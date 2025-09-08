# coding=utf-8

"""
Plex Subtitle Integration Service

This module provides the bridge between Plex content and Bazarr's existing subtitle system.
Instead of duplicating subtitle logic, it maps Plex content to the format expected by 
existing subtitle functions (movies.py, series.py, manual.py, etc.)
"""

import logging
from typing import Optional, Dict, Any, Tuple
from sqlalchemy import select

from app.database import database, TablePlexMovies, TablePlexEpisodes, TablePlexShows
from subtitles.wanted.movies import wanted_download_subtitles_movie 
from subtitles.wanted.series import wanted_download_subtitles
from subtitles.mass_download.movies import movies_download_subtitles
from subtitles.mass_download.series import episode_download_subtitles
from subtitles.manual import manual_search, manual_download_subtitle
from subtitles.download import generate_subtitles

logger = logging.getLogger(__name__)


class PlexSubtitleIntegrationService:
    """
    Service to integrate Plex content with Bazarr's existing subtitle workflow.
    
    This service acts as an adapter, mapping Plex data structures to the format
    expected by existing subtitle download functions, allowing full reuse of all
    existing subtitle providers, language profiles, and download logic.
    """
    
    def __init__(self):
        self.logger = logger
    
    # ===== MOVIE INTEGRATION =====
    
    def download_movie_subtitles(self, plex_id: int, languages: Optional[list] = None, 
                                providers: Optional[list] = None, **kwargs) -> Dict[str, Any]:
        """
        Download subtitles for a Plex movie using existing subtitle download logic.
        
        Args:
            plex_id: Plex movie ID
            languages: List of language codes to download
            providers: List of provider names to use
            **kwargs: Additional parameters
            
        Returns:
            Dict with download results and status
        """
        try:
            # Get Plex movie data
            movie = self._get_plex_movie(plex_id)
            if not movie:
                return {'success': False, 'error': f'Plex movie {plex_id} not found'}
            
            # Use existing subtitle download logic directly
            # This bypasses the need for Radarr database entries
            result = generate_subtitles(
                path=movie.path,
                profile_id=movie.profileId,
                languages=languages or self._get_missing_languages(movie),
                media_type='movie',
                minimum_score=kwargs.get('minimum_score'),
                forced_minimum_score=kwargs.get('forced_minimum_score'),
                providers=providers,
                title=movie.title,
                sceneName=getattr(movie, 'sceneName', ''),
                radarrId=plex_id  # Use actual plex_id for tracking
            )
            
            self.logger.info(f"Downloaded subtitles for Plex movie {plex_id}: {result}")
            return {'success': True, 'result': result}
            
        except Exception as e:
            self.logger.error(f"Failed to download subtitles for Plex movie {plex_id}: {e}")
            return {'success': False, 'error': str(e)}
    
    def _get_plex_movie(self, plex_id: int) -> Optional[Any]:
        """Get Plex movie data from database."""
        stmt = select(TablePlexMovies).where(TablePlexMovies.plexId == plex_id)
        return database.execute(stmt).first()
    
    def _map_plex_movie_to_radarr(self, plex_movie: Any, virtual_radarr_id: int) -> Dict[str, Any]:
        """
        Map Plex movie data to Radarr-compatible format.
        
        This allows existing Radarr subtitle functions to work with Plex content
        without modification.
        """
        return {
            'radarrId': virtual_radarr_id,
            'path': plex_movie.path,
            'title': plex_movie.title,
            'missing_subtitles': plex_movie.missing_subtitles or '[]',
            'audio_language': plex_movie.audio_language,
            'sceneName': getattr(plex_movie, 'sceneName', ''),  # May not exist in Plex
            'failedAttempts': plex_movie.failedAttempts or '[]',
            'profileId': plex_movie.profileId,
            'subtitles': plex_movie.subtitles or '[]',
            # Additional Plex-specific fields for reference
            'plex_id': plex_movie.plexId,
            'plex_guid': plex_movie.plexGuid,
            'imdb_id': plex_movie.imdbId,
            'tmdb_id': plex_movie.tmdbId,
        }
    
    # ===== EPISODE INTEGRATION =====
    
    def download_episode_subtitles(self, plex_episode_id: int, languages: Optional[list] = None,
                                  providers: Optional[list] = None, **kwargs) -> Dict[str, Any]:
        """
        Download subtitles for a Plex episode using existing subtitle download logic.
        
        Args:
            plex_episode_id: Plex episode ID
            languages: List of language codes to download
            providers: List of provider names to use
            **kwargs: Additional parameters
            
        Returns:
            Dict with download results
        """
        try:
            # Get Plex episode and show data
            episode_data = self._get_plex_episode_with_show(plex_episode_id)
            if not episode_data:
                return {'success': False, 'error': f'Plex episode {plex_episode_id} not found'}
            
            episode, show = episode_data
            
            # Use existing subtitle download logic directly
            result = generate_subtitles(
                path=episode.path,
                profile_id=episode.profileId,
                languages=languages or self._get_missing_languages(episode),
                media_type='series',
                minimum_score=kwargs.get('minimum_score'),
                forced_minimum_score=kwargs.get('forced_minimum_score'),
                providers=providers,
                title=f"{show.title} S{episode.season:02d}E{episode.episode:02d}",
                sceneName=getattr(episode, 'sceneName', ''),
                sonarrSeriesId=episode.plexShowId,
                sonarrEpisodeId=plex_episode_id
            )
            
            self.logger.info(f"Downloaded subtitles for Plex episode {plex_episode_id}: {result}")
            return {'success': True, 'result': result}
            
        except Exception as e:
            self.logger.error(f"Failed to download subtitles for Plex episode {plex_episode_id}: {e}")
            return {'success': False, 'error': str(e)}
    
    def _get_plex_episode_with_show(self, plex_episode_id: int) -> Optional[Tuple[Any, Any]]:
        """Get Plex episode with associated show data."""
        stmt = select(TablePlexEpisodes, TablePlexShows) \
            .select_from(TablePlexEpisodes) \
            .join(TablePlexShows, TablePlexEpisodes.plexShowId == TablePlexShows.plexId) \
            .where(TablePlexEpisodes.plexId == plex_episode_id)
        result = database.execute(stmt).first()
        
        if result:
            return result[0], result[1]  # episode, show
        return None
    
    def _get_missing_languages(self, item: Any) -> list:
        """
        Get list of missing subtitle languages for a Plex item.
        
        Args:
            item: Plex movie or episode object
            
        Returns:
            List of language codes that need subtitles
        """
        try:
            # Parse missing_subtitles JSON field
            import json
            missing_subtitles = json.loads(item.missing_subtitles or '[]')
            return [lang['code2'] for lang in missing_subtitles if 'code2' in lang]
        except (json.JSONDecodeError, KeyError, AttributeError):
            # Fallback: return empty list if parsing fails
            return []
    
    # ===== MANUAL SUBTITLE SEARCH =====
    
    def manual_search_subtitles(self, plex_id: int, media_type: str, **search_params) -> Dict[str, Any]:
        """
        Perform manual subtitle search for Plex content.
        
        Args:
            plex_id: Plex item ID (movie or episode)
            media_type: 'movie' or 'episode'
            **search_params: Search parameters (language, provider, etc.)
            
        Returns:
            Search results from existing manual search logic
        """
        try:
            if media_type == 'movie':
                movie = self._get_plex_movie(plex_id)
                if not movie:
                    return {'success': False, 'error': 'Movie not found'}
                
                # Use existing manual search logic
                return self._perform_manual_movie_search(movie, **search_params)
                
            elif media_type == 'episode':
                episode_data = self._get_plex_episode_with_show(plex_id)
                if not episode_data:
                    return {'success': False, 'error': 'Episode not found'}
                
                episode, show = episode_data
                return self._perform_manual_episode_search(episode, show, **search_params)
            
            else:
                return {'success': False, 'error': f'Unknown media type: {media_type}'}
                
        except Exception as e:
            self.logger.error(f"Manual search failed for Plex {media_type} {plex_id}: {e}")
            return {'success': False, 'error': str(e)}
    
    def _perform_manual_movie_search(self, movie: Any, **params) -> Dict[str, Any]:
        """Perform manual subtitle search for a movie using existing logic."""
        # Extract parameters with defaults
        providers = params.get('providers', [])
        
        # Use existing manual search function
        result = manual_search(
            path=movie.path,
            profile_id=movie.profileId,
            providers=providers,
            sceneName=getattr(movie, 'sceneName', ''),
            title=movie.title,
            media_type='movie'
        )
        
        return {'success': True, 'subtitles': result}
    
    def _perform_manual_episode_search(self, episode: Any, show: Any, **params) -> Dict[str, Any]:
        """Perform manual subtitle search for an episode using existing logic."""
        # Extract parameters with defaults
        providers = params.get('providers', [])
        
        # Use existing manual search function
        result = manual_search(
            path=episode.path,
            profile_id=episode.profileId,
            providers=providers,
            sceneName=getattr(episode, 'sceneName', ''),
            title=f"{show.title} S{episode.season:02d}E{episode.episode:02d}",
            media_type='series'
        )
        
        return {'success': True, 'subtitles': result}
    
    # ===== BULK OPERATIONS =====
    
    def bulk_download_library_subtitles(self, library_key: str) -> Dict[str, Any]:
        """
        Download subtitles for all content in a Plex library.
        
        Args:
            library_key: Plex library key
            
        Returns:
            Bulk operation results
        """
        results = {'movies': [], 'episodes': [], 'errors': []}
        
        try:
            # Get all movies in library
            movies_stmt = select(TablePlexMovies.plexId).where(
                TablePlexMovies.library_key == library_key
            )
            movies = database.execute(movies_stmt).fetchall()
            
            for movie_row in movies:
                movie_id = movie_row[0]
                result = self.download_movie_subtitles(movie_id)
                results['movies'].append({
                    'plex_id': movie_id,
                    'result': result
                })
            
            # Get all episodes in library (through shows)
            episodes_stmt = select(TablePlexEpisodes.plexId) \
                .select_from(TablePlexEpisodes) \
                .join(TablePlexShows, TablePlexEpisodes.plexShowId == TablePlexShows.plexId) \
                .where(TablePlexShows.library_key == library_key)
            episodes = database.execute(episodes_stmt).fetchall()
            
            for episode_row in episodes:
                episode_id = episode_row[0]
                result = self.download_episode_subtitles(episode_id)
                results['episodes'].append({
                    'plex_id': episode_id,
                    'result': result
                })
            
            return {
                'success': True,
                'processed': len(results['movies']) + len(results['episodes']),
                'results': results
            }
            
        except Exception as e:
            self.logger.error(f"Bulk download failed for library {library_key}: {e}")
            return {'success': False, 'error': str(e)}
    
    def download_manual_subtitle(self, plex_id: int, media_type: str, subtitle_data: str, 
                                provider: str, **kwargs) -> Dict[str, Any]:
        """
        Download a specific subtitle selected from manual search.
        
        Args:
            plex_id: Plex item ID (movie or episode)
            media_type: 'movie' or 'episode'
            subtitle_data: Base64 encoded subtitle object from manual search
            provider: Provider name
            **kwargs: Additional parameters
            
        Returns:
            Download result
        """
        try:
            if media_type == 'movie':
                movie = self._get_plex_movie(plex_id)
                if not movie:
                    return {'success': False, 'error': 'Movie not found'}
                
                result = manual_download_subtitle(
                    path=movie.path,
                    audio_language=kwargs.get('audio_language', movie.audio_language),
                    hi=kwargs.get('hi', 'False'),
                    forced=kwargs.get('forced', 'False'),
                    subtitle=subtitle_data,
                    provider=provider,
                    sceneName=getattr(movie, 'sceneName', ''),
                    title=movie.title,
                    media_type='movie',
                    use_original_format=kwargs.get('use_original_format', False),
                    profile_id=movie.profileId
                )
                
            elif media_type == 'episode':
                episode_data = self._get_plex_episode_with_show(plex_id)
                if not episode_data:
                    return {'success': False, 'error': 'Episode not found'}
                
                episode, show = episode_data
                result = manual_download_subtitle(
                    path=episode.path,
                    audio_language=kwargs.get('audio_language', episode.audio_language),
                    hi=kwargs.get('hi', 'False'),
                    forced=kwargs.get('forced', 'False'),
                    subtitle=subtitle_data,
                    provider=provider,
                    sceneName=getattr(episode, 'sceneName', ''),
                    title=f"{show.title} S{episode.season:02d}E{episode.episode:02d}",
                    media_type='series',
                    use_original_format=kwargs.get('use_original_format', False),
                    profile_id=episode.profileId
                )
            else:
                return {'success': False, 'error': f'Unknown media type: {media_type}'}
                
            return {'success': True, 'result': result}
            
        except Exception as e:
            self.logger.error(f"Manual download failed for Plex {media_type} {plex_id}: {e}")
            return {'success': False, 'error': str(e)}


# ===== SERVICE INSTANCE =====

# Global service instance for use throughout the application
plex_subtitle_service = PlexSubtitleIntegrationService()


# ===== CONVENIENCE FUNCTIONS =====

def download_plex_movie_subtitles(plex_id: int, **kwargs) -> Dict[str, Any]:
    """Convenience function to download movie subtitles."""
    return plex_subtitle_service.download_movie_subtitles(plex_id, **kwargs)


def download_plex_episode_subtitles(plex_episode_id: int, **kwargs) -> Dict[str, Any]:
    """Convenience function to download episode subtitles.""" 
    return plex_subtitle_service.download_episode_subtitles(plex_episode_id, **kwargs)


def search_plex_subtitles(plex_id: int, media_type: str, **kwargs) -> Dict[str, Any]:
    """Convenience function to search subtitles manually."""
    return plex_subtitle_service.manual_search_subtitles(plex_id, media_type, **kwargs)


def download_plex_manual_subtitle(plex_id: int, media_type: str, subtitle_data: str, 
                                  provider: str, **kwargs) -> Dict[str, Any]:
    """Convenience function to download manually selected subtitle."""
    return plex_subtitle_service.download_manual_subtitle(plex_id, media_type, subtitle_data, provider, **kwargs)


def bulk_download_plex_library(library_key: str) -> Dict[str, Any]:
    """Convenience function to download subtitles for entire library."""
    return plex_subtitle_service.bulk_download_library_subtitles(library_key)