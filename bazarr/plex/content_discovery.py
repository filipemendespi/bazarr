# coding=utf-8

import logging
import time
import re
import os
from datetime import datetime, timezone
from typing import List, Optional, Dict

from sqlalchemy import select, update, delete, insert
from sqlalchemy.exc import SQLAlchemyError, IntegrityError

from app.database import database, TablePlexLibraries, TablePlexShows, TablePlexEpisodes, TablePlexMovies
from app.config import settings
from .operations import get_plex_server

logger = logging.getLogger(__name__)


class PlexContentDiscoveryService:
    """
    Content discovery service for Plex media libraries.
    Discovers movies, TV shows, and episodes with metadata extraction.
    """
    
    def __init__(self):
        self.plex_server = None
        self.discovery_stats = {
            'movies_processed': 0,
            'movies_added': 0,
            'movies_updated': 0,
            'shows_processed': 0,
            'shows_added': 0,
            'shows_updated': 0,
            'episodes_processed': 0,
            'episodes_added': 0,
            'episodes_updated': 0,
            'discovery_start_time': None,
            'discovery_end_time': None,
            'errors': []
        }
    
    def _connect_to_plex(self) -> bool:
        """
        Establish connection to Plex server using existing authentication.
        Returns True if successful, False otherwise.
        """
        try:
            self.plex_server = get_plex_server()
            logger.info("Successfully connected to Plex server for content discovery")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to Plex server: {e}")
            self.discovery_stats['errors'].append(f"Connection failed: {str(e)}")
            return False
    
    def _extract_external_ids(self, item) -> Dict[str, Optional[str]]:
        """
        Extract external IDs (IMDB, TVDB, TMDB) from Plex GUID.
        Returns dictionary with external IDs.
        """
        ids = {'imdbId': None, 'tvdbId': None, 'tmdbId': None}
        
        if hasattr(item, 'guid'):
            guid = str(item.guid)
            
            # IMDB ID extraction
            if 'imdb://' in guid:
                match = re.search(r'imdb://(?:tt)?(\w+)', guid)
                if match:
                    ids['imdbId'] = f"tt{match.group(1)}"
            
            # TVDB ID extraction  
            if 'tvdb://' in guid:
                match = re.search(r'tvdb://(\d+)', guid)
                if match:
                    ids['tvdbId'] = match.group(1)
            
            # TMDB ID extraction
            if 'tmdb://' in guid:
                match = re.search(r'tmdb://(\d+)', guid)
                if match:
                    ids['tmdbId'] = match.group(1)
            
            # Handle Plex agents that include external IDs
            for guid_part in guid.split('?'):
                if 'imdb=' in guid_part:
                    match = re.search(r'imdb=(?:tt)?(\w+)', guid_part)
                    if match:
                        ids['imdbId'] = f"tt{match.group(1)}"
                if 'tvdb=' in guid_part:
                    match = re.search(r'tvdb=(\d+)', guid_part)
                    if match:
                        ids['tvdbId'] = match.group(1)
                if 'tmdb=' in guid_part:
                    match = re.search(r'tmdb=(\d+)', guid_part)
                    if match:
                        ids['tmdbId'] = match.group(1)
        
        return ids
    
    def discover_movies(self, library_key: str, library_title: str) -> int:
        """
        Discover all movies in a Plex library and save to database.
        Returns number of movies processed.
        """
        if not self._connect_to_plex():
            return 0
        
        try:
            # Convert key to int since Plex expects numeric section ID
            library = self.plex_server.library.sectionByID(int(library_key))
            movies = library.all()
            
            logger.info(f"Discovering {len(movies)} movies in library '{library_title}'")
            
            # Process movies in batches to avoid memory issues
            batch_size = 50
            for i in range(0, len(movies), batch_size):
                batch = movies[i:i + batch_size]
                
                for movie in batch:
                    try:
                        # Extract external IDs
                        external_ids = self._extract_external_ids(movie)
                        
                        # Get file path from media parts
                        file_path = None
                        if movie.media and len(movie.media) > 0:
                            if movie.media[0].parts and len(movie.media[0].parts) > 0:
                                file_path = movie.media[0].parts[0].file
                        
                        # Create movie data matching TablePlexMovies schema exactly
                        movie_data = {
                            'plexId': movie.ratingKey,
                            'plexGuid': str(movie.guid) if hasattr(movie, 'guid') else None,
                            'title': movie.title,
                            'year': movie.year,
                            'imdbId': external_ids['imdbId'],
                            'tmdbId': external_ids['tmdbId'],
                            'path': file_path or '',
                            'overview': movie.summary[:1024] if movie.summary else None,  # Limit overview length
                            'poster': movie.posterUrl if hasattr(movie, 'posterUrl') else None,
                            'fanart': movie.artUrl if hasattr(movie, 'artUrl') else None,
                            'duration': movie.duration if hasattr(movie, 'duration') else None,
                            'rating': float(movie.audienceRating) if hasattr(movie, 'audienceRating') and movie.audienceRating is not None else None,
                            'studio': movie.studio if hasattr(movie, 'studio') else None,
                            'genres': ', '.join([g.tag for g in movie.genres]) if hasattr(movie, 'genres') else None,
                            'directors': ', '.join([d.tag for d in movie.directors]) if hasattr(movie, 'directors') else None,
                            'writers': ', '.join([w.tag for w in movie.writers]) if hasattr(movie, 'writers') else None,
                            'actors': ', '.join([a.tag for a in movie.actors[:10]]) if hasattr(movie, 'actors') else None,  # Limit actors to first 10
                            'profileId': None  # Will be set by subtitle management logic
                        }
                        
                        # Check if movie exists
                        existing = database.execute(
                            select(TablePlexMovies)
                            .where(TablePlexMovies.plexId == movie_data['plexId'])
                        ).first()
                        
                        if existing:
                            # Update existing movie
                            database.execute(
                                update(TablePlexMovies)
                                .where(TablePlexMovies.plexId == movie_data['plexId'])
                                .values(**movie_data)
                            )
                            self.discovery_stats['movies_updated'] += 1
                            logger.debug(f"Updated movie: {movie.title}")
                        else:
                            # Insert new movie
                            database.execute(insert(TablePlexMovies).values(movie_data))
                            self.discovery_stats['movies_added'] += 1
                            logger.debug(f"Added movie: {movie.title}")
                        
                        self.discovery_stats['movies_processed'] += 1
                        
                    except Exception as e:
                        logger.error(f"Error processing movie '{movie.title}': {e}")
                        self.discovery_stats['errors'].append(f"Movie '{movie.title}': {str(e)}")
                
                # Small delay between batches to avoid overloading
                time.sleep(0.1)
            
            logger.info(f"Completed movie discovery for library '{library_title}': "
                       f"{self.discovery_stats['movies_processed']} processed, "
                       f"{self.discovery_stats['movies_added']} added, "
                       f"{self.discovery_stats['movies_updated']} updated")
            
            return self.discovery_stats['movies_processed']
            
        except Exception as e:
            logger.error(f"Failed to discover movies in library '{library_title}': {e}")
            self.discovery_stats['errors'].append(f"Movie discovery failed for '{library_title}': {str(e)}")
            return 0
    
    def discover_shows(self, library_key: str, library_title: str) -> int:
        """
        Discover all TV shows and episodes in a Plex library and save to database.
        Returns number of shows processed.
        """
        if not self._connect_to_plex():
            return 0
        
        try:
            # Convert key to int since Plex expects numeric section ID
            library = self.plex_server.library.sectionByID(int(library_key))
            shows = library.all()
            
            logger.info(f"Discovering {len(shows)} shows in library '{library_title}'")
            
            for show in shows:
                try:
                    # Extract external IDs for show
                    external_ids = self._extract_external_ids(show)
                    
                    # Get show path from first episode
                    show_path = None
                    try:
                        first_season = show.seasons()[0] if show.seasons() else None
                        if first_season:
                            first_episode = first_season.episodes()[0] if first_season.episodes() else None
                            if first_episode and first_episode.media and len(first_episode.media) > 0:
                                if first_episode.media[0].parts and len(first_episode.media[0].parts) > 0:
                                    # Extract show directory from episode path
                                    episode_path = first_episode.media[0].parts[0].file
                                    if episode_path:
                                        show_path = os.path.dirname(os.path.dirname(episode_path))
                    except:
                        pass
                    
                    # Create show data matching TablePlexShows schema exactly
                    show_data = {
                        'plexId': show.ratingKey,
                        'plexGuid': str(show.guid) if hasattr(show, 'guid') else None,
                        'title': show.title,
                        'year': show.year,
                        'imdbId': external_ids['imdbId'],
                        'tvdbId': int(external_ids['tvdbId']) if external_ids['tvdbId'] and external_ids['tvdbId'].isdigit() else None,
                        'tmdbId': external_ids['tmdbId'],
                        'path': show_path if show_path else f"show_{show.ratingKey}",  # Ensure unique path
                        'overview': show.summary[:1024] if show.summary else None,
                        'poster': show.posterUrl if hasattr(show, 'posterUrl') else None,
                        'fanart': show.artUrl if hasattr(show, 'artUrl') else None,
                        'network': show.studio if hasattr(show, 'studio') else None,
                        'status': show.status if hasattr(show, 'status') else None
                    }
                    
                    # Check if show exists
                    existing_show = database.execute(
                        select(TablePlexShows)
                        .where(TablePlexShows.plexId == show_data['plexId'])
                    ).first()
                    
                    if existing_show:
                        # Update existing show
                        database.execute(
                            update(TablePlexShows)
                            .where(TablePlexShows.plexId == show_data['plexId'])
                            .values(**show_data)
                        )
                        self.discovery_stats['shows_updated'] += 1
                        logger.debug(f"Updated show: {show.title}")
                    else:
                        # Insert new show
                        database.execute(insert(TablePlexShows).values(show_data))
                        self.discovery_stats['shows_added'] += 1
                        logger.debug(f"Added show: {show.title}")
                    
                    self.discovery_stats['shows_processed'] += 1
                    
                    # Store show info for episode processing
                    show_plex_id = show.ratingKey
                    show_tvdb_id = external_ids['tvdbId']
                    
                    # Process all episodes for this show
                    for season in show.seasons():
                        season_number = season.seasonNumber
                        
                        for episode in season.episodes():
                            try:
                                # Get episode file path
                                file_path = None
                                if episode.media and len(episode.media) > 0:
                                    if episode.media[0].parts and len(episode.media[0].parts) > 0:
                                        file_path = episode.media[0].parts[0].file
                                
                                # Create episode data matching TablePlexEpisodes schema exactly
                                episode_data = {
                                    'plexId': episode.ratingKey,
                                    'plexShowId': show_plex_id,
                                    'plexGuid': str(episode.guid) if hasattr(episode, 'guid') else None,
                                    'title': episode.title,
                                    'season': season_number,
                                    'episode': episode.index,
                                    'path': file_path or '',
                                    'overview': episode.summary[:1024] if episode.summary else None,
                                    'duration': episode.duration if hasattr(episode, 'duration') else None,
                                    'rating': float(episode.audienceRating) if hasattr(episode, 'audienceRating') and episode.audienceRating is not None else None,
                                    'directors': ', '.join([d.tag for d in episode.directors]) if hasattr(episode, 'directors') else None,
                                    'writers': ', '.join([w.tag for w in episode.writers]) if hasattr(episode, 'writers') else None,
                                    'missing_subtitles': None  # Will be populated later by subtitle logic
                                }
                                
                                # Check if episode exists
                                existing_episode = database.execute(
                                    select(TablePlexEpisodes)
                                    .where(TablePlexEpisodes.plexId == episode_data['plexId'])
                                ).first()
                                
                                if existing_episode:
                                    # Update existing episode
                                    database.execute(
                                        update(TablePlexEpisodes)
                                        .where(TablePlexEpisodes.plexId == episode_data['plexId'])
                                        .values(**episode_data)
                                    )
                                    self.discovery_stats['episodes_updated'] += 1
                                    logger.debug(f"Updated episode: {episode.title}")
                                else:
                                    # Insert new episode
                                    database.execute(insert(TablePlexEpisodes).values(episode_data))
                                    self.discovery_stats['episodes_added'] += 1
                                    logger.debug(f"Added episode: {episode.title}")
                                
                                self.discovery_stats['episodes_processed'] += 1
                                
                            except Exception as e:
                                logger.error(f"Error processing episode '{episode.title}': {e}")
                                self.discovery_stats['errors'].append(f"Episode '{episode.title}': {str(e)}")
                
                except Exception as e:
                    logger.error(f"Error processing show '{show.title}': {e}")
                    self.discovery_stats['errors'].append(f"Show '{show.title}': {str(e)}")
            
            logger.info(f"Completed show discovery for library '{library_title}': "
                       f"{self.discovery_stats['shows_processed']} shows processed, "
                       f"{self.discovery_stats['shows_added']} shows added, "
                       f"{self.discovery_stats['shows_updated']} shows updated, "
                       f"{self.discovery_stats['episodes_processed']} episodes processed, "
                       f"{self.discovery_stats['episodes_added']} episodes added, "
                       f"{self.discovery_stats['episodes_updated']} episodes updated")
            
            return self.discovery_stats['shows_processed']
            
        except Exception as e:
            logger.error(f"Failed to discover shows in library '{library_title}': {e}")
            self.discovery_stats['errors'].append(f"Show discovery failed for '{library_title}': {str(e)}")
            return 0
    
    def discover_all_content(self) -> Dict:
        """
        Discover all content across enabled Plex libraries.
        Returns discovery statistics dictionary.
        """
        self.discovery_stats['discovery_start_time'] = datetime.now(timezone.utc)
        logger.info("Starting comprehensive content discovery across all Plex libraries")
        
        try:
            # Get enabled libraries from database
            enabled_libraries = database.execute(
                select(TablePlexLibraries)
                .where(
                    (TablePlexLibraries.enabled == 1) &
                    (TablePlexLibraries.sync_enabled == 1)
                )
            ).scalars().all()
            
            if not enabled_libraries:
                logger.warning("No enabled libraries found for content discovery")
                return self._finalize_discovery_stats(success=True)
            
            logger.info(f"Discovering content from {len(enabled_libraries)} enabled libraries")
            logger.debug(f"Libraries found: {[lib.__dict__ if hasattr(lib, '__dict__') else str(lib) for lib in enabled_libraries]}")
            
            for library in enabled_libraries:
                logger.info(f"Processing library: {library.title} (key: {library.key}, type: {library.type})")
                try:
                    if library.type == 'movie':
                        self.discover_movies(library.key, library.title)
                    elif library.type == 'show':
                        self.discover_shows(library.key, library.title)
                    else:
                        logger.debug(f"Skipping unsupported library type: {library.type}")
                except Exception as e:
                    logger.error(f"Error processing library {library.title}: {e}")
                    self.discovery_stats['errors'].append(f"Library {library.title}: {str(e)}")
            
            logger.info("Content discovery completed successfully")
            return self._finalize_discovery_stats(success=True)
            
        except Exception as e:
            logger.error(f"Content discovery failed: {e}")
            self.discovery_stats['errors'].append(f"Discovery failed: {str(e)}")
            return self._finalize_discovery_stats(success=False)
    
    def _finalize_discovery_stats(self, success: bool) -> Dict:
        """
        Finalize discovery statistics and return them.
        """
        self.discovery_stats['discovery_end_time'] = datetime.now(timezone.utc)
        self.discovery_stats['success'] = success
        
        if self.discovery_stats['discovery_start_time']:
            duration = (self.discovery_stats['discovery_end_time'] - self.discovery_stats['discovery_start_time']).total_seconds()
            self.discovery_stats['duration_seconds'] = duration
        
        return self.discovery_stats.copy()


def discover_plex_content() -> Dict:
    """
    Convenience function to perform Plex content discovery.
    
    Returns:
        Dictionary with discovery statistics and results.
    """
    discovery_service = PlexContentDiscoveryService()
    return discovery_service.discover_all_content()