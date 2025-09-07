# coding=utf-8

import logging
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Tuple
import time

from sqlalchemy import select, update, delete
from sqlalchemy.exc import SQLAlchemyError

from app.database import database, TablePlexLibraries, TablePlexShows, TablePlexEpisodes, TablePlexMovies
from app.config import settings
from .operations import get_plex_server
from .conflict_resolution import create_conflict_resolver

logger = logging.getLogger(__name__)


class PlexLibrarySyncService:
    """
    Core library synchronization service for Plex integration.
    Handles discovery, metadata extraction, and incremental sync.
    """
    
    def __init__(self, conflict_strategy: str = "plex_wins"):
        self.plex_server = None
        self.conflict_resolver = create_conflict_resolver(conflict_strategy)
        self.sync_stats = {
            'libraries_processed': 0,
            'libraries_added': 0,
            'libraries_updated': 0,
            'conflicts_detected': 0,
            'conflicts_resolved': 0,
            'sync_start_time': None,
            'sync_end_time': None,
            'errors': []
        }
    
    def _connect_to_plex(self) -> bool:
        """
        Establish connection to Plex server using existing authentication.
        Returns True if successful, False otherwise.
        """
        try:
            self.plex_server = get_plex_server()
            logger.info("Successfully connected to Plex server")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to Plex server: {e}")
            self.sync_stats['errors'].append(f"Connection failed: {str(e)}")
            return False
    
    def discover_libraries(self) -> List[Dict]:
        """
        Discover all movie and TV show libraries from Plex server.
        Returns list of library metadata dictionaries.
        """
        if not self.plex_server:
            if not self._connect_to_plex():
                return []
        
        discovered_libraries = []
        
        try:
            # Get all libraries from Plex
            all_sections = self.plex_server.library.sections()
            logger.info(f"Discovered {len(all_sections)} total sections on Plex server")
            
            for section in all_sections:
                # Only process movie and show libraries
                if section.type in ['movie', 'show']:
                    library_data = {
                        'key': str(section.key),
                        'title': section.title,
                        'type': section.type,
                        'agent': getattr(section, 'agent', None),
                        'scanner': getattr(section, 'scanner', None),
                        'language': getattr(section, 'language', None),
                        'uuid': getattr(section, 'uuid', None),
                        'enabled': 1,  # Default enabled
                        'sync_enabled': 1,  # Default sync enabled
                        'last_scan': None,
                        'scan_interval': 3600,  # Default 1 hour
                        'created_at_timestamp': datetime.now(timezone.utc),
                        'updated_at_timestamp': datetime.now(timezone.utc)
                    }
                    discovered_libraries.append(library_data)
                    logger.info(f"Discovered {section.type} library: {section.title} (key: {section.key})")
        
        except Exception as e:
            logger.error(f"Failed to discover libraries: {e}")
            self.sync_stats['errors'].append(f"Library discovery failed: {str(e)}")
        
        return discovered_libraries
    
    def sync_library_metadata(self, library_data: Dict) -> bool:
        """
        Sync single library metadata to database.
        Returns True if successful, False otherwise.
        """
        try:
            # Check if library exists
            existing = database.execute(
                select(TablePlexLibraries)
                .where(TablePlexLibraries.key == library_data['key'])
            ).first()
            
            if existing:
                # Update existing library
                database.execute(
                    update(TablePlexLibraries)
                    .where(TablePlexLibraries.key == library_data['key'])
                    .values(
                        title=library_data['title'],
                        type=library_data['type'],
                        agent=library_data.get('agent'),
                        scanner=library_data.get('scanner'),
                        language=library_data.get('language'),
                        uuid=library_data.get('uuid'),
                        updated_at_timestamp=datetime.now(timezone.utc)
                    )
                )
                logger.info(f"Updated library: {library_data['title']}")
                self.sync_stats['libraries_updated'] += 1
            else:
                # Insert new library
                new_library = TablePlexLibraries(**library_data)
                database.session.add(new_library)
                logger.info(f"Added new library: {library_data['title']}")
                self.sync_stats['libraries_added'] += 1
            
            database.session.commit()
            self.sync_stats['libraries_processed'] += 1
            return True
            
        except SQLAlchemyError as e:
            database.session.rollback()
            logger.error(f"Database error syncing library {library_data.get('title', 'Unknown')}: {e}")
            self.sync_stats['errors'].append(f"DB error for library {library_data.get('title')}: {str(e)}")
            return False
        except Exception as e:
            database.session.rollback()
            logger.error(f"Unexpected error syncing library {library_data.get('title', 'Unknown')}: {e}")
            self.sync_stats['errors'].append(f"Sync error for library {library_data.get('title')}: {str(e)}")
            return False
    
    def get_enabled_libraries(self) -> List[Tuple[str, str, str]]:
        """
        Get list of enabled libraries from database.
        Returns list of (key, title, type) tuples.
        """
        try:
            libraries = database.execute(
                select(TablePlexLibraries)
                .where(
                    (TablePlexLibraries.enabled == 1) &
                    (TablePlexLibraries.sync_enabled == 1)
                )
            ).all()
            
            return [(lib.key, lib.title, lib.type) for lib in libraries]
            
        except Exception as e:
            logger.error(f"Failed to get enabled libraries: {e}")
            return []
    
    def update_library_scan_time(self, library_key: str) -> bool:
        """
        Update the last_scan timestamp for a library.
        Returns True if successful.
        """
        try:
            database.execute(
                update(TablePlexLibraries)
                .where(TablePlexLibraries.key == library_key)
                .values(last_scan=datetime.now(timezone.utc))
            )
            database.session.commit()
            logger.debug(f"Updated scan time for library {library_key}")
            return True
        except Exception as e:
            database.session.rollback()
            logger.error(f"Failed to update scan time for library {library_key}: {e}")
            return False
    
    def cleanup_removed_libraries(self, current_library_keys: List[str]) -> int:
        """
        Remove libraries from database that no longer exist in Plex.
        Returns number of libraries removed.
        """
        try:
            # Find libraries to remove
            libraries_to_remove = database.execute(
                select(TablePlexLibraries)
                .where(~TablePlexLibraries.key.in_(current_library_keys))
            ).all()
            
            removed_count = len(libraries_to_remove)
            
            if removed_count > 0:
                # Delete libraries not in current list
                database.execute(
                    delete(TablePlexLibraries)
                    .where(~TablePlexLibraries.key.in_(current_library_keys))
                )
                database.session.commit()
                logger.info(f"Removed {removed_count} libraries that no longer exist in Plex")
            
            return removed_count
            
        except Exception as e:
            database.session.rollback()
            logger.error(f"Failed to cleanup removed libraries: {e}")
            return 0
    
    def perform_full_library_sync(self, cleanup_removed: bool = True) -> Dict:
        """
        Perform complete library synchronization process.
        Returns sync statistics dictionary.
        """
        self.sync_stats['sync_start_time'] = datetime.now(timezone.utc)
        logger.info("Starting full library synchronization")
        
        try:
            # Step 1: Connect to Plex server
            if not self._connect_to_plex():
                return self._finalize_sync_stats(success=False)
            
            # Step 2: Discover all libraries
            discovered_libraries = self.discover_libraries()
            if not discovered_libraries:
                logger.warning("No media libraries discovered")
                return self._finalize_sync_stats(success=True)
            
            logger.info(f"Discovered {len(discovered_libraries)} media libraries")
            
            # Step 3: Sync each library
            current_library_keys = []
            for library_data in discovered_libraries:
                if self.sync_library_metadata(library_data):
                    current_library_keys.append(library_data['key'])
            
            # Step 4: Cleanup removed libraries if requested
            removed_count = 0
            if cleanup_removed and current_library_keys:
                removed_count = self.cleanup_removed_libraries(current_library_keys)
            
            # Step 5: Log results
            logger.info(f"Library sync completed successfully. "
                       f"Processed: {self.sync_stats['libraries_processed']}, "
                       f"Added: {self.sync_stats['libraries_added']}, "
                       f"Updated: {self.sync_stats['libraries_updated']}, "
                       f"Removed: {removed_count}")
            
            return self._finalize_sync_stats(success=True)
            
        except Exception as e:
            logger.error(f"Full library sync failed: {e}")
            self.sync_stats['errors'].append(f"Full sync failed: {str(e)}")
            return self._finalize_sync_stats(success=False)
    
    def perform_incremental_sync(self, max_age_hours: int = 24) -> Dict:
        """
        Perform incremental synchronization for libraries that need updating.
        Only syncs libraries that haven't been scanned within max_age_hours.
        Returns sync statistics dictionary.
        """
        self.sync_stats['sync_start_time'] = datetime.now(timezone.utc)
        logger.info(f"Starting incremental library synchronization (max age: {max_age_hours}h)")
        
        try:
            # Get libraries that need scanning
            cutoff_time = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
            
            libraries_to_sync = database.execute(
                select(TablePlexLibraries)
                .where(
                    (TablePlexLibraries.enabled == 1) &
                    (TablePlexLibraries.sync_enabled == 1) &
                    (
                        (TablePlexLibraries.last_scan.is_(None)) |
                        (TablePlexLibraries.last_scan < cutoff_time)
                    )
                )
            ).all()
            
            if not libraries_to_sync:
                logger.info("No libraries require incremental sync")
                return self._finalize_sync_stats(success=True)
            
            logger.info(f"Found {len(libraries_to_sync)} libraries requiring sync")
            
            # Connect to Plex
            if not self._connect_to_plex():
                return self._finalize_sync_stats(success=False)
            
            # Sync each library that needs it
            for lib in libraries_to_sync:
                try:
                    # Get current library data from Plex
                    section = self.plex_server.library.section(lib.title)
                    
                    library_data = {
                        'key': str(section.key),
                        'title': section.title,
                        'type': section.type,
                        'agent': getattr(section, 'agent', None),
                        'scanner': getattr(section, 'scanner', None),
                        'language': getattr(section, 'language', None),
                        'uuid': getattr(section, 'uuid', None),
                        'updated_at_timestamp': datetime.now(timezone.utc)
                    }
                    
                    if self.sync_library_metadata(library_data):
                        self.update_library_scan_time(lib.key)
                    
                except Exception as e:
                    logger.error(f"Failed to sync library {lib.title}: {e}")
                    self.sync_stats['errors'].append(f"Incremental sync failed for {lib.title}: {str(e)}")
            
            logger.info("Incremental library sync completed")
            return self._finalize_sync_stats(success=True)
            
        except Exception as e:
            logger.error(f"Incremental library sync failed: {e}")
            self.sync_stats['errors'].append(f"Incremental sync failed: {str(e)}")
            return self._finalize_sync_stats(success=False)
    
    def _finalize_sync_stats(self, success: bool) -> Dict:
        """
        Finalize sync statistics and return them.
        """
        self.sync_stats['sync_end_time'] = datetime.now(timezone.utc)
        self.sync_stats['success'] = success
        
        if self.sync_stats['sync_start_time']:
            duration = (self.sync_stats['sync_end_time'] - self.sync_stats['sync_start_time']).total_seconds()
            self.sync_stats['duration_seconds'] = duration
        
        return self.sync_stats.copy()


    def perform_incremental_sync(self, since_timestamp: Optional[datetime] = None) -> Dict:
        """
        Perform incremental synchronization based on updatedAt timestamps.
        Only sync items that have been updated since the last sync.
        
        Args:
            since_timestamp: Sync items updated since this timestamp. If None, 
                           uses last successful sync timestamp from database.
        
        Returns:
            Dictionary with sync statistics and results.
        """
        self.sync_stats['sync_start_time'] = datetime.now(timezone.utc)
        logger.info("Starting incremental library synchronization")
        
        try:
            # Step 1: Connect to Plex server
            if not self._connect_to_plex():
                return self._finalize_sync_stats(success=False)
            
            # Step 2: Determine sync timestamp
            if since_timestamp is None:
                since_timestamp = self._get_last_sync_timestamp()
            
            if since_timestamp:
                logger.info(f"Performing incremental sync since: {since_timestamp}")
            else:
                logger.info("No previous sync timestamp found, performing full sync")
                return self.perform_full_library_sync()
            
            # Step 3: Get enabled libraries from database
            enabled_libraries = database.execute(
                select(TablePlexLibraries)
                .where(TablePlexLibraries.sync_enabled == 1)
            ).all()
            
            if not enabled_libraries:
                logger.warning("No enabled libraries found for incremental sync")
                return self._finalize_sync_stats(success=True)
            
            # Step 4: Perform incremental sync for each enabled library
            total_updated = 0
            for library in enabled_libraries:
                updated_count = self._sync_library_incremental(library, since_timestamp)
                total_updated += updated_count
                
                # Update library's last_scan timestamp
                database.execute(
                    update(TablePlexLibraries)
                    .where(TablePlexLibraries.key == library.key)
                    .values(
                        last_scan=datetime.now(timezone.utc),
                        updated_at_timestamp=datetime.now(timezone.utc)
                    )
                )
            
            # Step 5: Log results
            conflicts_summary = self.conflict_resolver.get_conflicts_summary()
            logger.info(f"Incremental sync completed successfully. "
                       f"Libraries processed: {len(enabled_libraries)}, "
                       f"Items updated: {total_updated}, "
                       f"Conflicts detected: {conflicts_summary['total_conflicts']}, "
                       f"Conflicts resolved: {self.sync_stats['conflicts_resolved']}")
            
            return self._finalize_sync_stats(success=True)
            
        except Exception as e:
            logger.error(f"Incremental sync failed: {e}")
            self.sync_stats['errors'].append(f"Incremental sync failed: {str(e)}")
            return self._finalize_sync_stats(success=False)
    
    def _get_last_sync_timestamp(self) -> Optional[datetime]:
        """
        Get the timestamp of the last successful sync from database.
        Returns the oldest last_scan timestamp across all enabled libraries.
        """
        try:
            result = database.execute(
                select(TablePlexLibraries.last_scan)
                .where(
                    TablePlexLibraries.sync_enabled == 1,
                    TablePlexLibraries.last_scan.is_not(None)
                )
                .order_by(TablePlexLibraries.last_scan.asc())
            ).first()
            
            return result[0] if result else None
            
        except Exception as e:
            logger.error(f"Failed to get last sync timestamp: {e}")
            return None
    
    def _sync_library_incremental(self, library, since_timestamp: datetime) -> int:
        """
        Perform incremental sync for a specific library.
        Returns number of items updated.
        """
        updated_count = 0
        
        try:
            section = self.plex_server.library.section(library.title)
            logger.info(f"Starting incremental sync for library: {library.title}")
            
            if library.type == 'movie':
                updated_count = self._sync_movies_incremental(section, library.key, since_timestamp)
            elif library.type == 'show':
                updated_count = self._sync_shows_incremental(section, library.key, since_timestamp)
            
            logger.info(f"Incremental sync completed for {library.title}: {updated_count} items updated")
            
        except Exception as e:
            logger.error(f"Failed to sync library {library.title} incrementally: {e}")
            self.sync_stats['errors'].append(f"Incremental sync failed for library {library.title}: {str(e)}")
        
        return updated_count
    
    def _sync_movies_incremental(self, section, library_key: str, since_timestamp: datetime) -> int:
        """
        Sync movies that have been updated since the given timestamp.
        """
        updated_count = 0
        
        try:
            # Get all movies from Plex (we'll filter by timestamp)
            movies = section.all()
            
            for movie in movies:
                # Check if movie was updated since last sync
                if hasattr(movie, 'updatedAt') and movie.updatedAt > since_timestamp:
                    # Check if movie exists in database
                    existing = database.execute(
                        select(TablePlexMovies)
                        .where(TablePlexMovies.plex_id == str(movie.ratingKey))
                    ).first()
                    
                    if existing:
                        # Update existing movie
                        self._update_movie_metadata(movie, library_key)
                    else:
                        # Add new movie
                        self._add_movie_metadata(movie, library_key)
                    
                    updated_count += 1
            
        except Exception as e:
            logger.error(f"Failed to sync movies incrementally: {e}")
            
        return updated_count
    
    def _sync_shows_incremental(self, section, library_key: str, since_timestamp: datetime) -> int:
        """
        Sync TV shows and episodes that have been updated since the given timestamp.
        """
        updated_count = 0
        
        try:
            shows = section.all()
            
            for show in shows:
                # Check if show was updated since last sync
                if hasattr(show, 'updatedAt') and show.updatedAt > since_timestamp:
                    # Update show metadata
                    existing_show = database.execute(
                        select(TablePlexShows)
                        .where(TablePlexShows.plex_id == str(show.ratingKey))
                    ).first()
                    
                    if existing_show:
                        self._update_show_metadata(show, library_key)
                    else:
                        self._add_show_metadata(show, library_key)
                    
                    # Check episodes for updates
                    for episode in show.episodes():
                        if hasattr(episode, 'updatedAt') and episode.updatedAt > since_timestamp:
                            existing_episode = database.execute(
                                select(TablePlexEpisodes)
                                .where(TablePlexEpisodes.plex_id == str(episode.ratingKey))
                            ).first()
                            
                            if existing_episode:
                                self._update_episode_metadata(episode, str(show.ratingKey))
                            else:
                                self._add_episode_metadata(episode, str(show.ratingKey))
                            
                            updated_count += 1
                    
                    updated_count += 1
            
        except Exception as e:
            logger.error(f"Failed to sync shows incrementally: {e}")
            
        return updated_count
    
    def _update_movie_metadata(self, movie, library_key: str):
        """Update existing movie metadata in database with conflict resolution."""
        try:
            # Get existing database record
            existing = database.execute(
                select(TablePlexMovies)
                .where(TablePlexMovies.plex_id == str(movie.ratingKey))
            ).first()
            
            if not existing:
                logger.warning(f"Movie not found in database for update: {movie.title}")
                return
            
            # Get Plex update timestamp
            plex_updated_at = getattr(movie, 'updatedAt', datetime.now(timezone.utc))
            
            # Resolve conflicts using conflict resolver
            resolved_data = self.conflict_resolver.resolve_movie_conflict(
                movie, existing, plex_updated_at
            )
            
            # Update with resolved data
            database.execute(
                update(TablePlexMovies)
                .where(TablePlexMovies.plex_id == str(movie.ratingKey))
                .values(**resolved_data)
            )
            
            # Update conflict statistics
            conflicts = self.conflict_resolver.get_conflicts_summary()
            if conflicts['total_conflicts'] > self.sync_stats['conflicts_detected']:
                self.sync_stats['conflicts_detected'] = conflicts['total_conflicts']
                self.sync_stats['conflicts_resolved'] += 1
            
        except Exception as e:
            logger.error(f"Failed to update movie metadata for {movie.title}: {e}")
    
    def _update_show_metadata(self, show, library_key: str):
        """Update existing show metadata in database with conflict resolution."""
        try:
            # Get existing database record
            existing = database.execute(
                select(TablePlexShows)
                .where(TablePlexShows.plex_id == str(show.ratingKey))
            ).first()
            
            if not existing:
                logger.warning(f"Show not found in database for update: {show.title}")
                return
            
            # Get Plex update timestamp
            plex_updated_at = getattr(show, 'updatedAt', datetime.now(timezone.utc))
            
            # Resolve conflicts using conflict resolver
            resolved_data = self.conflict_resolver.resolve_show_conflict(
                show, existing, plex_updated_at
            )
            
            # Update with resolved data
            database.execute(
                update(TablePlexShows)
                .where(TablePlexShows.plex_id == str(show.ratingKey))
                .values(**resolved_data)
            )
            
            # Update conflict statistics
            conflicts = self.conflict_resolver.get_conflicts_summary()
            if conflicts['total_conflicts'] > self.sync_stats['conflicts_detected']:
                self.sync_stats['conflicts_detected'] = conflicts['total_conflicts']
                self.sync_stats['conflicts_resolved'] += 1
            
        except Exception as e:
            logger.error(f"Failed to update show metadata for {show.title}: {e}")
    
    def _update_episode_metadata(self, episode, show_plex_id: str):
        """Update existing episode metadata in database with conflict resolution."""
        try:
            # Get existing database record
            existing = database.execute(
                select(TablePlexEpisodes)
                .where(TablePlexEpisodes.plex_id == str(episode.ratingKey))
            ).first()
            
            if not existing:
                logger.warning(f"Episode not found in database for update: {episode.title}")
                return
            
            # Get Plex update timestamp
            plex_updated_at = getattr(episode, 'updatedAt', datetime.now(timezone.utc))
            
            # Resolve conflicts using conflict resolver
            resolved_data = self.conflict_resolver.resolve_episode_conflict(
                episode, existing, plex_updated_at
            )
            
            # Update with resolved data
            database.execute(
                update(TablePlexEpisodes)
                .where(TablePlexEpisodes.plex_id == str(episode.ratingKey))
                .values(**resolved_data)
            )
            
            # Update conflict statistics
            conflicts = self.conflict_resolver.get_conflicts_summary()
            if conflicts['total_conflicts'] > self.sync_stats['conflicts_detected']:
                self.sync_stats['conflicts_detected'] = conflicts['total_conflicts']
                self.sync_stats['conflicts_resolved'] += 1
            
        except Exception as e:
            logger.error(f"Failed to update episode metadata for {episode.title}: {e}")
    
    def _add_movie_metadata(self, movie, library_key: str):
        """Add new movie metadata to database (reuses content discovery logic)."""
        from .content_discovery import PlexContentDiscoveryService
        discovery_service = PlexContentDiscoveryService()
        # Use the existing movie discovery logic
        discovery_service._process_single_movie(movie, library_key, "Incremental Sync")
    
    def _add_show_metadata(self, show, library_key: str):
        """Add new show metadata to database (reuses content discovery logic)."""
        from .content_discovery import PlexContentDiscoveryService
        discovery_service = PlexContentDiscoveryService()
        # Use the existing show discovery logic
        discovery_service._process_single_show(show, library_key, "Incremental Sync")
    
    def _add_episode_metadata(self, episode, show_plex_id: str):
        """Add new episode metadata to database (reuses content discovery logic)."""
        from .content_discovery import PlexContentDiscoveryService
        discovery_service = PlexContentDiscoveryService()
        # Use the existing episode discovery logic
        discovery_service._process_single_episode(episode, show_plex_id)


def sync_plex_libraries(full_sync: bool = True, cleanup_removed: bool = True, 
                       conflict_strategy: str = "plex_wins") -> Dict:
    """
    Convenience function to perform Plex library synchronization.
    
    Args:
        full_sync: If True, performs full sync. If False, performs incremental sync.
        cleanup_removed: If True, removes libraries that no longer exist in Plex.
        conflict_strategy: Strategy for resolving update conflicts ("plex_wins", "database_wins", "merge_metadata", "manual_review").
    
    Returns:
        Dictionary with sync statistics and results.
    """
    sync_service = PlexLibrarySyncService(conflict_strategy=conflict_strategy)
    
    if full_sync:
        return sync_service.perform_full_library_sync(cleanup_removed=cleanup_removed)
    else:
        return sync_service.perform_incremental_sync()
