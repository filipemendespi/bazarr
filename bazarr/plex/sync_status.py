# coding=utf-8

import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional

from sqlalchemy import select, func, text

from app.database import (database, TablePlexLibraries, TablePlexMovies,
                         TablePlexShows, TablePlexEpisodes)

logger = logging.getLogger(__name__)


class PlexSyncStatusService:
    """
    Service for tracking and reporting Plex synchronization status and statistics.
    """

    def __init__(self):
        self.cache_ttl = 300  # 5 minutes cache TTL
        self._cache = {}
        self._cache_timestamps = {}

    def get_sync_dashboard(self) -> Dict[str, Any]:
        """
        Get comprehensive sync status dashboard data.

        Returns:
            Dictionary with sync status, statistics, and health information
        """
        try:
            # Check cache first
            if self._is_cached('dashboard'):
                return self._cache['dashboard']

            dashboard_data = {
                'sync_status': self.get_sync_status(),
                'library_stats': self.get_library_statistics(),
                'content_stats': self.get_content_statistics(),
                'recent_activity': self.get_recent_sync_activity(),
                'health_indicators': self.get_health_indicators(),
                'last_updated': datetime.now(timezone.utc).isoformat()
            }

            # Cache the results
            self._cache['dashboard'] = dashboard_data
            self._cache_timestamps['dashboard'] = datetime.now(timezone.utc)

            return dashboard_data

        except Exception as e:
            logger.error(f"Error generating sync dashboard: {e}")
            return {
                'error': str(e),
                'last_updated': datetime.now(timezone.utc).isoformat()
            }

    def get_sync_status(self) -> Dict[str, Any]:
        """
        Get current synchronization status for all libraries.

        Returns:
            Dictionary with sync status information
        """
        try:
            # Get all libraries with sync status
            libraries = database.execute(
                select(TablePlexLibraries.key, TablePlexLibraries.title,
                      TablePlexLibraries.type, TablePlexLibraries.enabled,
                      TablePlexLibraries.sync_enabled, TablePlexLibraries.last_scan,
                      TablePlexLibraries.scan_interval, TablePlexLibraries.updated_at_timestamp)
            ).all()

            now = datetime.now(timezone.utc)
            library_status = []

            for lib in libraries:
                next_sync = None
                sync_health = "unknown"

                if lib.last_scan and lib.scan_interval:
                    next_sync = lib.last_scan + timedelta(seconds=lib.scan_interval)

                    # Determine sync health
                    if lib.sync_enabled:
                        if now > next_sync:
                            sync_health = "overdue"
                        elif (next_sync - now).total_seconds() < lib.scan_interval * 0.1:
                            sync_health = "due_soon"
                        else:
                            sync_health = "healthy"
                    else:
                        sync_health = "disabled"

                library_status.append({
                    'key': lib.key,
                    'title': lib.title,
                    'type': lib.type,
                    'enabled': bool(lib.enabled),
                    'sync_enabled': bool(lib.sync_enabled),
                    'last_scan': lib.last_scan.isoformat() if lib.last_scan else None,
                    'next_scan': next_sync.isoformat() if next_sync else None,
                    'sync_health': sync_health,
                    'scan_interval_hours': round(lib.scan_interval / 3600, 2) if lib.scan_interval else None
                })

            # Overall sync status
            enabled_libraries = [lib for lib in library_status if lib['sync_enabled']]
            overdue_libraries = [lib for lib in enabled_libraries if lib['sync_health'] == 'overdue']

            overall_status = "healthy"
            if len(overdue_libraries) > 0:
                if len(overdue_libraries) >= len(enabled_libraries) * 0.5:
                    overall_status = "critical"
                else:
                    overall_status = "warning"

            return {
                'overall_status': overall_status,
                'total_libraries': len(libraries),
                'enabled_libraries': len(enabled_libraries),
                'overdue_libraries': len(overdue_libraries),
                'libraries': library_status
            }

        except Exception as e:
            logger.error(f"Error getting sync status: {e}")
            return {'error': str(e)}

    def get_library_statistics(self) -> Dict[str, Any]:
        """
        Get statistics for each library.

        Returns:
            Dictionary with library statistics
        """
        try:
            stats = {}

            # Get library counts
            libraries = database.execute(
                select(TablePlexLibraries.key, TablePlexLibraries.title, TablePlexLibraries.type)
            ).all()

            for lib in libraries:
                lib_stats = {
                    'title': lib.title,
                    'type': lib.type,
                    'content_count': 0,
                    'last_content_update': None
                }

                if lib.type == 'movie':
                    # Movie statistics
                    movie_stats = database.execute(
                        select(func.count(TablePlexMovies.plexId).label('count'),
                              func.max(TablePlexMovies.updated_at_timestamp).label('last_update'))
                        .where(TablePlexMovies.library_key == lib.key)
                    ).first()

                    if movie_stats:
                        lib_stats['content_count'] = movie_stats.count or 0
                        lib_stats['last_content_update'] = movie_stats.last_update.isoformat() if movie_stats.last_update else None

                elif lib.type == 'show':
                    # TV show statistics
                    show_stats = database.execute(
                        select(func.count(TablePlexShows.plexId).label('show_count'),
                              func.max(TablePlexShows.updated_at_timestamp).label('show_last_update'))
                        .where(TablePlexShows.library_key == lib.key)
                    ).first()

                    episode_stats = database.execute(
                        select(func.count(TablePlexEpisodes.plexId).label('episode_count'),
                              func.max(TablePlexEpisodes.updated_at_timestamp).label('episode_last_update'))
                        .join(TablePlexShows, TablePlexEpisodes.plexShowId == TablePlexShows.plexId)
                        .where(TablePlexShows.library_key == lib.key)
                    ).first()

                    if show_stats and episode_stats:
                        lib_stats['content_count'] = {
                            'shows': show_stats.show_count or 0,
                            'episodes': episode_stats.episode_count or 0
                        }

                        # Use the more recent timestamp
                        last_updates = [
                            show_stats.show_last_update,
                            episode_stats.episode_last_update
                        ]
                        last_updates = [dt for dt in last_updates if dt is not None]

                        if last_updates:
                            lib_stats['last_content_update'] = max(last_updates).isoformat()

                stats[lib.key] = lib_stats

            return stats

        except Exception as e:
            logger.error(f"Error getting library statistics: {e}")
            return {'error': str(e)}

    def get_content_statistics(self) -> Dict[str, Any]:
        """
        Get overall content statistics across all libraries.

        Returns:
            Dictionary with content statistics
        """
        try:
            # Movie statistics
            movie_stats = database.execute(
                select(func.count(TablePlexMovies.plexId).label('total_movies'),
                      func.count(func.distinct(TablePlexMovies.library_key)).label('movie_libraries'))
            ).first()

            # Show statistics
            show_stats = database.execute(
                select(func.count(TablePlexShows.plexId).label('total_shows'),
                      func.count(func.distinct(TablePlexShows.library_key)).label('show_libraries'))
            ).first()

            # Episode statistics
            episode_stats = database.execute(
                select(func.count(TablePlexEpisodes.plexId).label('total_episodes'))
            ).first()

            # Recent additions (last 24 hours)
            recent_cutoff = datetime.now(timezone.utc) - timedelta(hours=24)

            recent_movies = database.execute(
                select(func.count(TablePlexMovies.plexId))
                .where(TablePlexMovies.created_at_timestamp >= recent_cutoff)
            ).scalar() or 0

            recent_shows = database.execute(
                select(func.count(TablePlexShows.plexId))
                .where(TablePlexShows.created_at_timestamp >= recent_cutoff)
            ).scalar() or 0

            recent_episodes = database.execute(
                select(func.count(TablePlexEpisodes.plexId))
                .where(TablePlexEpisodes.created_at_timestamp >= recent_cutoff)
            ).scalar() or 0

            return {
                'total_content': {
                    'movies': movie_stats.total_movies if movie_stats else 0,
                    'shows': show_stats.total_shows if show_stats else 0,
                    'episodes': episode_stats.total_episodes if episode_stats else 0
                },
                'libraries': {
                    'movie_libraries': movie_stats.movie_libraries if movie_stats else 0,
                    'show_libraries': show_stats.show_libraries if show_stats else 0
                },
                'recent_additions_24h': {
                    'movies': recent_movies,
                    'shows': recent_shows,
                    'episodes': recent_episodes
                }
            }

        except Exception as e:
            logger.error(f"Error getting content statistics: {e}")
            return {'error': str(e)}

    def get_recent_sync_activity(self, hours: int = 24) -> List[Dict[str, Any]]:
        """
        Get recent synchronization activity.

        Args:
            hours: Number of hours to look back

        Returns:
            List of recent activity events
        """
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
            activity = []

            # Recent movie updates
            recent_movies = database.execute(
                select(TablePlexMovies.title, TablePlexMovies.updated_at_timestamp,
                      TablePlexLibraries.title.label('library_title'))
                .join(TablePlexLibraries, TablePlexMovies.library_key == TablePlexLibraries.key)
                .where(TablePlexMovies.updated_at_timestamp >= cutoff)
                .order_by(TablePlexMovies.updated_at_timestamp.desc())
                .limit(10)
            ).all()

            for movie in recent_movies:
                activity.append({
                    'type': 'movie_update',
                    'title': movie.title,
                    'library': movie.library_title,
                    'timestamp': movie.updated_at_timestamp.isoformat()
                })

            # Recent show updates
            recent_shows = database.execute(
                select(TablePlexShows.title, TablePlexShows.updated_at_timestamp,
                      TablePlexLibraries.title.label('library_title'))
                .join(TablePlexLibraries, TablePlexShows.library_key == TablePlexLibraries.key)
                .where(TablePlexShows.updated_at_timestamp >= cutoff)
                .order_by(TablePlexShows.updated_at_timestamp.desc())
                .limit(10)
            ).all()

            for show in recent_shows:
                activity.append({
                    'type': 'show_update',
                    'title': show.title,
                    'library': show.library_title,
                    'timestamp': show.updated_at_timestamp.isoformat()
                })

            # Recent episode updates
            recent_episodes = database.execute(
                select(TablePlexEpisodes.title, TablePlexEpisodes.updated_at_timestamp,
                      TablePlexShows.title.label('show_title'),
                      TablePlexLibraries.title.label('library_title'))
                .join(TablePlexShows, TablePlexEpisodes.plexShowId == TablePlexShows.plexId)
                .join(TablePlexLibraries, TablePlexShows.library_key == TablePlexLibraries.key)
                .where(TablePlexEpisodes.updated_at_timestamp >= cutoff)
                .order_by(TablePlexEpisodes.updated_at_timestamp.desc())
                .limit(10)
            ).all()

            for episode in recent_episodes:
                activity.append({
                    'type': 'episode_update',
                    'title': f"{episode.show_title} - {episode.title}",
                    'library': episode.library_title,
                    'timestamp': episode.updated_at_timestamp.isoformat()
                })

            # Sort by timestamp and limit
            activity.sort(key=lambda x: x['timestamp'], reverse=True)
            return activity[:20]  # Return top 20 recent activities

        except Exception as e:
            logger.error(f"Error getting recent sync activity: {e}")
            return []

    def get_health_indicators(self) -> Dict[str, Any]:
        """
        Get health indicators for the Plex sync system.

        Returns:
            Dictionary with health metrics
        """
        try:
            now = datetime.now(timezone.utc)

            # Check for stale data (not updated in last 24 hours)
            stale_cutoff = now - timedelta(hours=24)

            stale_libraries = database.execute(
                select(func.count(TablePlexLibraries.key))
                .where(
                    TablePlexLibraries.sync_enabled == 1,
                    TablePlexLibraries.last_scan < stale_cutoff
                )
            ).scalar() or 0

            # Check for missing content paths or metadata
            movies_no_path = database.execute(
                select(func.count(TablePlexMovies.plexId))
                .where(TablePlexMovies.path.is_(None))
            ).scalar() or 0

            shows_no_path = database.execute(
                select(func.count(TablePlexShows.plexId))
                .where(TablePlexShows.path.is_(None))
            ).scalar() or 0

            # Database connection health
            try:
                database.execute(text("SELECT 1")).scalar()
                db_health = "healthy"
            except Exception:
                db_health = "error"

            # Overall health score (0-100)
            health_score = 100

            if stale_libraries > 0:
                health_score -= min(stale_libraries * 10, 30)

            if movies_no_path > 0 or shows_no_path > 0:
                health_score -= min((movies_no_path + shows_no_path) * 2, 20)

            if db_health != "healthy":
                health_score -= 50

            health_score = max(health_score, 0)

            return {
                'health_score': health_score,
                'database_health': db_health,
                'stale_libraries': stale_libraries,
                'data_quality': {
                    'movies_missing_path': movies_no_path,
                    'shows_missing_path': shows_no_path
                },
                'recommendations': self._generate_health_recommendations(
                    stale_libraries, movies_no_path, shows_no_path, db_health
                )
            }

        except Exception as e:
            logger.error(f"Error getting health indicators: {e}")
            return {'error': str(e)}

    def _generate_health_recommendations(self, stale_libs: int, movies_no_path: int,
                                       shows_no_path: int, db_health: str) -> List[str]:
        """Generate health recommendations based on metrics."""
        recommendations = []

        if stale_libs > 0:
            recommendations.append(f"Consider running manual sync for {stale_libs} stale libraries")

        if movies_no_path > 0:
            recommendations.append(f"Fix missing paths for {movies_no_path} movies")

        if shows_no_path > 0:
            recommendations.append(f"Fix missing paths for {shows_no_path} shows")

        if db_health != "healthy":
            recommendations.append("Check database connection and integrity")

        if not recommendations:
            recommendations.append("All systems operating normally")

        return recommendations

    def _is_cached(self, key: str) -> bool:
        """Check if data is cached and still valid."""
        if key not in self._cache or key not in self._cache_timestamps:
            return False

        cache_age = (datetime.now(timezone.utc) - self._cache_timestamps[key]).total_seconds()
        return cache_age < self.cache_ttl

    def clear_cache(self):
        """Clear all cached data."""
        self._cache.clear()
        self._cache_timestamps.clear()


# Singleton instance
sync_status_service = PlexSyncStatusService()
