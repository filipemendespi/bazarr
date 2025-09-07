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

logger = logging.getLogger(__name__)


class PlexLibrarySyncService:
    """
    Core library synchronization service for Plex integration.
    Handles discovery, metadata extraction, and incremental sync.
    """
    
    def __init__(self):
        self.plex_server = None
        self.sync_stats = {
            'libraries_processed': 0,
            'libraries_added': 0,
            'libraries_updated': 0,
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


def sync_plex_libraries(full_sync: bool = True, cleanup_removed: bool = True) -> Dict:
    """
    Convenience function to perform Plex library synchronization.
    
    Args:
        full_sync: If True, performs full sync. If False, performs incremental sync.
        cleanup_removed: If True, removes libraries that no longer exist in Plex.
    
    Returns:
        Dictionary with sync statistics and results.
    """
    sync_service = PlexLibrarySyncService()
    
    if full_sync:
        return sync_service.perform_full_library_sync(cleanup_removed=cleanup_removed)
    else:
        return sync_service.perform_incremental_sync()


def get_library_sync_status() -> Dict:
    """
    Get current status of library synchronization.
    
    Returns:
        Dictionary with library counts and sync information.
    """
    try:
        # Get all libraries from database
        all_libraries = database.execute(select(TablePlexLibraries)).all()
        
        # Count by type
        movie_count = sum(1 for lib in all_libraries if lib.type == 'movie')
        show_count = sum(1 for lib in all_libraries if lib.type == 'show')
        enabled_count = sum(1 for lib in all_libraries if lib.enabled and lib.sync_enabled)
        
        # Get most recent sync time
        last_sync = None
        for lib in all_libraries:
            if lib.last_scan and (not last_sync or lib.last_scan > last_sync):
                last_sync = lib.last_scan
        
        # Format library list
        libraries_list = []
        for lib in all_libraries:
            libraries_list.append({
                'key': lib.key,
                'title': lib.title,
                'type': lib.type,
                'enabled': bool(lib.enabled),
                'sync_enabled': bool(lib.sync_enabled),
                'last_scan': lib.last_scan.isoformat() if lib.last_scan else None
            })
        
        return {
            'total_libraries': len(all_libraries),
            'movie_libraries': movie_count,
            'show_libraries': show_count,
            'enabled_libraries': enabled_count,
            'last_sync': last_sync.isoformat() if last_sync else None,
            'libraries': libraries_list
        }
        
    except Exception as e:
        logger.error(f"Failed to get library sync status: {e}")
        return {
            'error': str(e),
            'total_libraries': 0,
            'movie_libraries': 0,
            'show_libraries': 0,
            'enabled_libraries': 0,
            'last_sync': None,
            'libraries': []
        }