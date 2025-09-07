# coding=utf-8

import logging
from flask import request
from flask_restx import Resource, Namespace, fields

from ..utils import authenticate
from ..plex.sync import sync_plex_libraries
from ..plex.sync_status import sync_status_service

logger = logging.getLogger(__name__)

api_ns_plex_sync = Namespace('Plex Sync', description='Plex synchronization management and monitoring')

# API Models
sync_status_model = api_ns_plex_sync.model('SyncStatus', {
    'overall_status': fields.String(description='Overall sync health status'),
    'total_libraries': fields.Integer(description='Total number of libraries'),
    'enabled_libraries': fields.Integer(description='Number of enabled libraries'),
    'overdue_libraries': fields.Integer(description='Number of overdue libraries'),
})

library_stats_model = api_ns_plex_sync.model('LibraryStats', {
    'title': fields.String(description='Library title'),
    'type': fields.String(description='Library type (movie/show)'),
    'content_count': fields.Raw(description='Content count (integer for movies, object for shows)'),
})

sync_response_model = api_ns_plex_sync.model('SyncResponse', {
    'success': fields.Boolean(description='Sync operation success'),
    'message': fields.String(description='Sync result message'),
    'statistics': fields.Raw(description='Sync statistics'),
})


@api_ns_plex_sync.route('/status')
class PlexSyncStatus(Resource):
    @authenticate
    @api_ns_plex_sync.response(200, 'Success')
    @api_ns_plex_sync.response(401, 'Not Authenticated')
    @api_ns_plex_sync.response(500, 'Internal server error')
    def get(self):
        """Get Plex sync status dashboard"""
        try:
            dashboard_data = sync_status_service.get_sync_dashboard()
            return dashboard_data, 200
        except Exception as e:
            logger.error(f"Error getting sync status: {e}")
            return {'error': str(e)}, 500


@api_ns_plex_sync.route('/libraries')
class PlexLibraryStats(Resource):
    @authenticate
    @api_ns_plex_sync.response(200, 'Success')
    @api_ns_plex_sync.response(401, 'Not Authenticated')
    @api_ns_plex_sync.response(500, 'Internal server error')
    def get(self):
        """Get Plex library statistics"""
        try:
            library_stats = sync_status_service.get_library_statistics()
            return library_stats, 200
        except Exception as e:
            logger.error(f"Error getting library statistics: {e}")
            return {'error': str(e)}, 500


@api_ns_plex_sync.route('/sync/full')
class PlexFullSync(Resource):
    @authenticate
    @api_ns_plex_sync.response(200, 'Sync completed successfully')
    @api_ns_plex_sync.response(401, 'Not Authenticated')
    @api_ns_plex_sync.response(500, 'Sync failed')
    def post(self):
        """Trigger full Plex library synchronization"""
        try:
            # Get optional parameters
            cleanup_removed = request.args.get('cleanup_removed', 'true').lower() == 'true'
            conflict_strategy = request.args.get('conflict_strategy', 'plex_wins')
            
            logger.info(f"Starting full Plex sync (cleanup_removed: {cleanup_removed}, "
                       f"conflict_strategy: {conflict_strategy})")
            
            # Perform synchronization
            sync_results = sync_plex_libraries(
                full_sync=True,
                cleanup_removed=cleanup_removed,
                conflict_strategy=conflict_strategy
            )
            
            if sync_results.get('success', False):
                # Clear cache to refresh status
                sync_status_service.clear_cache()
                
                return {
                    'success': True,
                    'message': 'Full synchronization completed successfully',
                    'statistics': sync_results
                }, 200
            else:
                return {
                    'success': False,
                    'message': 'Full synchronization failed',
                    'statistics': sync_results
                }, 500
                
        except Exception as e:
            logger.error(f"Error during full sync: {e}")
            return {
                'success': False,
                'message': f'Sync error: {str(e)}',
                'error': str(e)
            }, 500


@api_ns_plex_sync.route('/sync/incremental')
class PlexIncrementalSync(Resource):
    @authenticate
    @api_ns_plex_sync.response(200, 'Incremental sync completed successfully')
    @api_ns_plex_sync.response(401, 'Not Authenticated')
    @api_ns_plex_sync.response(500, 'Incremental sync failed')
    def post(self):
        """Trigger incremental Plex library synchronization"""
        try:
            # Get optional parameters
            conflict_strategy = request.args.get('conflict_strategy', 'plex_wins')
            
            logger.info(f"Starting incremental Plex sync (conflict_strategy: {conflict_strategy})")
            
            # Perform incremental synchronization
            sync_results = sync_plex_libraries(
                full_sync=False,
                conflict_strategy=conflict_strategy
            )
            
            if sync_results.get('success', False):
                # Clear cache to refresh status
                sync_status_service.clear_cache()
                
                return {
                    'success': True,
                    'message': 'Incremental synchronization completed successfully',
                    'statistics': sync_results
                }, 200
            else:
                return {
                    'success': False,
                    'message': 'Incremental synchronization failed',
                    'statistics': sync_results
                }, 500
                
        except Exception as e:
            logger.error(f"Error during incremental sync: {e}")
            return {
                'success': False,
                'message': f'Incremental sync error: {str(e)}',
                'error': str(e)
            }, 500


@api_ns_plex_sync.route('/health')
class PlexSyncHealth(Resource):
    @authenticate
    @api_ns_plex_sync.response(200, 'Success')
    @api_ns_plex_sync.response(401, 'Not Authenticated')
    @api_ns_plex_sync.response(500, 'Internal server error')
    def get(self):
        """Get Plex sync health indicators"""
        try:
            health_data = sync_status_service.get_health_indicators()
            return health_data, 200
        except Exception as e:
            logger.error(f"Error getting health indicators: {e}")
            return {'error': str(e)}, 500


@api_ns_plex_sync.route('/activity')
class PlexSyncActivity(Resource):
    @authenticate
    @api_ns_plex_sync.response(200, 'Success')
    @api_ns_plex_sync.response(401, 'Not Authenticated')
    @api_ns_plex_sync.response(500, 'Internal server error')
    def get(self):
        """Get recent Plex sync activity"""
        try:
            # Get optional hours parameter
            hours = int(request.args.get('hours', '24'))
            activity_data = sync_status_service.get_recent_sync_activity(hours=hours)
            return {
                'activity': activity_data,
                'hours_requested': hours
            }, 200
        except Exception as e:
            logger.error(f"Error getting sync activity: {e}")
            return {'error': str(e)}, 500


@api_ns_plex_sync.route('/cache/clear')
class PlexSyncClearCache(Resource):
    @authenticate
    @api_ns_plex_sync.response(200, 'Cache cleared successfully')
    @api_ns_plex_sync.response(401, 'Not Authenticated')
    def post(self):
        """Clear sync status cache"""
        try:
            sync_status_service.clear_cache()
            return {'message': 'Sync status cache cleared successfully'}, 200
        except Exception as e:
            logger.error(f"Error clearing cache: {e}")
            return {'error': str(e)}, 500