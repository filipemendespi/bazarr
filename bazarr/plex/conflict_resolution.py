# coding=utf-8

import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from enum import Enum

from sqlalchemy import select, update
from sqlalchemy.exc import SQLAlchemyError

from app.database import (database, TablePlexLibraries, TablePlexMovies, 
                         TablePlexShows, TablePlexEpisodes)

logger = logging.getLogger(__name__)


class ConflictResolutionStrategy(Enum):
    """Strategies for resolving update conflicts."""
    PLEX_WINS = "plex_wins"        # Plex timestamp takes precedence
    DATABASE_WINS = "database_wins" # Database timestamp takes precedence
    MERGE_METADATA = "merge_metadata"  # Merge non-conflicting metadata
    MANUAL_REVIEW = "manual_review"    # Flag for manual review


class PlexConflictResolver:
    """
    Handles conflict resolution for concurrent updates between 
    Plex server changes and local database modifications.
    """
    
    def __init__(self, strategy: ConflictResolutionStrategy = ConflictResolutionStrategy.PLEX_WINS):
        self.strategy = strategy
        self.conflicts_detected = []
        
    def resolve_movie_conflict(self, plex_movie, database_movie, plex_updated_at: datetime) -> Dict[str, Any]:
        """
        Resolve conflicts for movie metadata updates.
        
        Args:
            plex_movie: Plex movie object
            database_movie: Database movie record
            plex_updated_at: When the movie was updated in Plex
            
        Returns:
            Dictionary with resolved metadata values
        """
        try:
            database_updated_at = database_movie.updated_at_timestamp
            
            # Check for timestamp conflict
            if self._has_timestamp_conflict(plex_updated_at, database_updated_at):
                conflict_data = {
                    'type': 'movie',
                    'plex_id': str(plex_movie.ratingKey),
                    'title': plex_movie.title,
                    'plex_timestamp': plex_updated_at,
                    'database_timestamp': database_updated_at,
                    'strategy_used': self.strategy.value
                }
                
                logger.warning(f"Conflict detected for movie {plex_movie.title} "
                             f"(Plex: {plex_updated_at}, DB: {database_updated_at})")
                
                self.conflicts_detected.append(conflict_data)
                
                return self._resolve_conflict(
                    plex_data=self._extract_movie_metadata(plex_movie),
                    database_data=self._extract_movie_database_data(database_movie),
                    plex_timestamp=plex_updated_at,
                    database_timestamp=database_updated_at
                )
            else:
                # No conflict, use Plex data
                return self._extract_movie_metadata(plex_movie)
                
        except Exception as e:
            logger.error(f"Error resolving movie conflict: {e}")
            # Fallback to Plex data on error
            return self._extract_movie_metadata(plex_movie)
    
    def resolve_show_conflict(self, plex_show, database_show, plex_updated_at: datetime) -> Dict[str, Any]:
        """
        Resolve conflicts for TV show metadata updates.
        
        Args:
            plex_show: Plex show object
            database_show: Database show record
            plex_updated_at: When the show was updated in Plex
            
        Returns:
            Dictionary with resolved metadata values
        """
        try:
            database_updated_at = database_show.updated_at_timestamp
            
            # Check for timestamp conflict
            if self._has_timestamp_conflict(plex_updated_at, database_updated_at):
                conflict_data = {
                    'type': 'show',
                    'plex_id': str(plex_show.ratingKey),
                    'title': plex_show.title,
                    'plex_timestamp': plex_updated_at,
                    'database_timestamp': database_updated_at,
                    'strategy_used': self.strategy.value
                }
                
                logger.warning(f"Conflict detected for show {plex_show.title} "
                             f"(Plex: {plex_updated_at}, DB: {database_updated_at})")
                
                self.conflicts_detected.append(conflict_data)
                
                return self._resolve_conflict(
                    plex_data=self._extract_show_metadata(plex_show),
                    database_data=self._extract_show_database_data(database_show),
                    plex_timestamp=plex_updated_at,
                    database_timestamp=database_updated_at
                )
            else:
                # No conflict, use Plex data
                return self._extract_show_metadata(plex_show)
                
        except Exception as e:
            logger.error(f"Error resolving show conflict: {e}")
            # Fallback to Plex data on error
            return self._extract_show_metadata(plex_show)
    
    def resolve_episode_conflict(self, plex_episode, database_episode, plex_updated_at: datetime) -> Dict[str, Any]:
        """
        Resolve conflicts for episode metadata updates.
        
        Args:
            plex_episode: Plex episode object
            database_episode: Database episode record
            plex_updated_at: When the episode was updated in Plex
            
        Returns:
            Dictionary with resolved metadata values
        """
        try:
            database_updated_at = database_episode.updated_at_timestamp
            
            # Check for timestamp conflict
            if self._has_timestamp_conflict(plex_updated_at, database_updated_at):
                conflict_data = {
                    'type': 'episode',
                    'plex_id': str(plex_episode.ratingKey),
                    'title': plex_episode.title,
                    'plex_timestamp': plex_updated_at,
                    'database_timestamp': database_updated_at,
                    'strategy_used': self.strategy.value
                }
                
                logger.warning(f"Conflict detected for episode {plex_episode.title} "
                             f"(Plex: {plex_updated_at}, DB: {database_updated_at})")
                
                self.conflicts_detected.append(conflict_data)
                
                return self._resolve_conflict(
                    plex_data=self._extract_episode_metadata(plex_episode),
                    database_data=self._extract_episode_database_data(database_episode),
                    plex_timestamp=plex_updated_at,
                    database_timestamp=database_updated_at
                )
            else:
                # No conflict, use Plex data
                return self._extract_episode_metadata(plex_episode)
                
        except Exception as e:
            logger.error(f"Error resolving episode conflict: {e}")
            # Fallback to Plex data on error
            return self._extract_episode_metadata(plex_episode)
    
    def _has_timestamp_conflict(self, plex_timestamp: datetime, database_timestamp: Optional[datetime]) -> bool:
        """
        Check if there's a timestamp conflict between Plex and database updates.
        
        Args:
            plex_timestamp: Plex update timestamp
            database_timestamp: Database update timestamp
            
        Returns:
            True if there's a conflict, False otherwise
        """
        if database_timestamp is None:
            return False
        
        # Consider it a conflict if both were updated within a small time window
        # but database timestamp is newer than Plex timestamp
        time_diff = abs((plex_timestamp - database_timestamp).total_seconds())
        
        # Conflict if updates happened within 30 seconds of each other
        # and database was updated more recently
        return time_diff < 30 and database_timestamp > plex_timestamp
    
    def _resolve_conflict(self, plex_data: Dict[str, Any], database_data: Dict[str, Any], 
                         plex_timestamp: datetime, database_timestamp: datetime) -> Dict[str, Any]:
        """
        Apply the conflict resolution strategy to resolve data conflicts.
        
        Args:
            plex_data: Metadata from Plex
            database_data: Metadata from database
            plex_timestamp: Plex update timestamp
            database_timestamp: Database update timestamp
            
        Returns:
            Resolved metadata dictionary
        """
        if self.strategy == ConflictResolutionStrategy.PLEX_WINS:
            # Plex data always wins
            resolved = plex_data.copy()
            resolved['conflict_resolution'] = 'plex_wins'
            
        elif self.strategy == ConflictResolutionStrategy.DATABASE_WINS:
            # Database data always wins
            resolved = database_data.copy()
            resolved['conflict_resolution'] = 'database_wins'
            
        elif self.strategy == ConflictResolutionStrategy.MERGE_METADATA:
            # Merge non-conflicting fields, use most recent for conflicts
            resolved = self._merge_metadata(plex_data, database_data, 
                                          plex_timestamp, database_timestamp)
            resolved['conflict_resolution'] = 'merged'
            
        else:  # MANUAL_REVIEW
            # Keep existing data and flag for manual review
            resolved = database_data.copy()
            resolved['conflict_resolution'] = 'manual_review_required'
            resolved['needs_review'] = True
        
        # Always update the timestamp to track resolution
        resolved['updated_at_timestamp'] = datetime.now(timezone.utc)
        resolved['conflict_resolved_at'] = datetime.now(timezone.utc)
        
        return resolved
    
    def _merge_metadata(self, plex_data: Dict[str, Any], database_data: Dict[str, Any],
                       plex_timestamp: datetime, database_timestamp: datetime) -> Dict[str, Any]:
        """
        Merge metadata from Plex and database, preferring more recent data for conflicts.
        
        Args:
            plex_data: Metadata from Plex
            database_data: Metadata from database
            plex_timestamp: Plex update timestamp
            database_timestamp: Database update timestamp
            
        Returns:
            Merged metadata dictionary
        """
        resolved = database_data.copy()
        
        # Fields that should always come from Plex (authoritative source)
        plex_authoritative_fields = [
            'title', 'year', 'duration', 'rating', 'summary', 'tagline', 
            'studio', 'originally_available_at', 'season_number', 'episode_number'
        ]
        
        # Use more recent timestamp to decide on conflicts
        use_plex_for_conflicts = plex_timestamp >= database_timestamp
        
        for field in plex_authoritative_fields:
            if field in plex_data:
                if field in database_data:
                    # Field exists in both - use strategy to decide
                    if plex_data[field] != database_data[field]:
                        if use_plex_for_conflicts:
                            resolved[field] = plex_data[field]
                        # else keep database value (already in resolved)
                    else:
                        # Values are the same, use Plex value
                        resolved[field] = plex_data[field]
                else:
                    # Field only in Plex data
                    resolved[field] = plex_data[field]
        
        return resolved
    
    def _extract_movie_metadata(self, movie) -> Dict[str, Any]:
        """Extract metadata from Plex movie object."""
        return {
            'title': movie.title,
            'year': getattr(movie, 'year', None),
            'rating': float(movie.audienceRating) if hasattr(movie, 'audienceRating') and movie.audienceRating is not None else None,
            'duration': getattr(movie, 'duration', None),
            'summary': getattr(movie, 'summary', None),
            'tagline': getattr(movie, 'tagline', None),
            'studio': getattr(movie, 'studio', None)
        }
    
    def _extract_show_metadata(self, show) -> Dict[str, Any]:
        """Extract metadata from Plex show object."""
        return {
            'title': show.title,
            'year': getattr(show, 'year', None),
            'rating': float(show.audienceRating) if hasattr(show, 'audienceRating') and show.audienceRating is not None else None,
            'summary': getattr(show, 'summary', None),
            'studio': getattr(show, 'studio', None)
        }
    
    def _extract_episode_metadata(self, episode) -> Dict[str, Any]:
        """Extract metadata from Plex episode object."""
        return {
            'title': episode.title,
            'season_number': getattr(episode, 'seasonNumber', None),
            'episode_number': getattr(episode, 'index', None),
            'rating': float(episode.audienceRating) if hasattr(episode, 'audienceRating') and episode.audienceRating is not None else None,
            'summary': getattr(episode, 'summary', None),
            'originally_available_at': getattr(episode, 'originallyAvailableAt', None)
        }
    
    def _extract_movie_database_data(self, movie_record) -> Dict[str, Any]:
        """Extract metadata from database movie record."""
        return {
            'title': movie_record.title,
            'year': movie_record.year,
            'rating': movie_record.rating,
            'duration': movie_record.duration,
            'summary': movie_record.summary,
            'tagline': movie_record.tagline,
            'studio': movie_record.studio
        }
    
    def _extract_show_database_data(self, show_record) -> Dict[str, Any]:
        """Extract metadata from database show record."""
        return {
            'title': show_record.title,
            'year': show_record.year,
            'rating': show_record.rating,
            'summary': show_record.summary,
            'studio': show_record.studio
        }
    
    def _extract_episode_database_data(self, episode_record) -> Dict[str, Any]:
        """Extract metadata from database episode record."""
        return {
            'title': episode_record.title,
            'season_number': episode_record.season_number,
            'episode_number': episode_record.episode_number,
            'rating': episode_record.rating,
            'summary': episode_record.summary,
            'originally_available_at': episode_record.originally_available_at
        }
    
    def get_conflicts_summary(self) -> Dict[str, Any]:
        """
        Get a summary of conflicts detected during the last resolution session.
        
        Returns:
            Dictionary with conflict statistics and details
        """
        return {
            'total_conflicts': len(self.conflicts_detected),
            'conflicts_by_type': {
                'movies': len([c for c in self.conflicts_detected if c['type'] == 'movie']),
                'shows': len([c for c in self.conflicts_detected if c['type'] == 'show']),
                'episodes': len([c for c in self.conflicts_detected if c['type'] == 'episode'])
            },
            'strategy_used': self.strategy.value,
            'conflicts': self.conflicts_detected
        }
    
    def clear_conflicts(self):
        """Clear the conflicts list for a new resolution session."""
        self.conflicts_detected = []


def create_conflict_resolver(strategy: str = "plex_wins") -> PlexConflictResolver:
    """
    Factory function to create a conflict resolver with specified strategy.
    
    Args:
        strategy: Conflict resolution strategy name
        
    Returns:
        PlexConflictResolver instance
    """
    try:
        strategy_enum = ConflictResolutionStrategy(strategy)
        return PlexConflictResolver(strategy_enum)
    except ValueError:
        logger.warning(f"Unknown conflict resolution strategy: {strategy}. Using default 'plex_wins'")
        return PlexConflictResolver(ConflictResolutionStrategy.PLEX_WINS)