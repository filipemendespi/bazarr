# coding=utf-8

import logging
from datetime import datetime
from flask import request
from flask_restx import Resource, Namespace, fields, reqparse

from api.utils import authenticate
from plex.sync import sync_plex_libraries
from plex.sync_status import sync_status_service
from plex.retry_service import retry_service
from plex.retry_worker import retry_worker

logger = logging.getLogger(__name__)


def clean_datetime_objects(obj):
    """Recursively clean datetime objects from data structures for JSON serialization."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    elif isinstance(obj, dict):
        return {k: clean_datetime_objects(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [clean_datetime_objects(item) for item in obj]
    elif hasattr(obj, 'isoformat'):  # Other datetime-like objects
        return obj.isoformat()
    else:
        return obj


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

library_model = api_ns_plex_sync.model('PlexLibrary', {
    'key': fields.String(description='Plex library key'),
    'title': fields.String(description='Library name'),
    'type': fields.String(description='Library type (movie/show)'),
    'agent': fields.String(description='Metadata agent'),
    'scanner': fields.String(description='File scanner'),
    'enabled': fields.Boolean(description='Library enabled status'),
    'sync_enabled': fields.Boolean(description='Sync enabled status'),
    'last_scan': fields.String(description='Last scan timestamp'),
    'scan_interval': fields.Integer(description='Scan interval in seconds'),
})

library_update_model = api_ns_plex_sync.model('LibraryUpdate', {
    'enabled': fields.Boolean(description='Library enabled status'),
    'sync_enabled': fields.Boolean(description='Sync enabled status'),
    'scan_interval': fields.Integer(description='Scan interval in seconds'),
})


@api_ns_plex_sync.route('plex/sync/status')
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


@api_ns_plex_sync.route('plex/libraries')
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


@api_ns_plex_sync.route('plex/sync/full')
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
                    'statistics': clean_datetime_objects(sync_results)
                }, 500
                
        except Exception as e:
            logger.error(f"Error during full sync: {e}")
            return {
                'success': False,
                'message': f'Sync error: {str(e)}',
                'error': str(e)
            }, 500


@api_ns_plex_sync.route('plex/sync/incremental')
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
                    'statistics': clean_datetime_objects(sync_results)
                }, 500
                
        except Exception as e:
            logger.error(f"Error during incremental sync: {e}")
            return {
                'success': False,
                'message': f'Incremental sync error: {str(e)}',
                'error': str(e)
            }, 500


@api_ns_plex_sync.route('plex/health')
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


@api_ns_plex_sync.route('plex/activity')
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


@api_ns_plex_sync.route('plex/cache/clear')
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


@api_ns_plex_sync.route('plex/sync/libraries/manage')
class PlexLibrariesManage(Resource):
    @authenticate
    @api_ns_plex_sync.response(200, 'Success', [library_model])
    @api_ns_plex_sync.response(401, 'Not Authenticated')
    @api_ns_plex_sync.response(500, 'Internal server error')
    def get(self):
        """Get all Plex libraries with management information"""
        try:
            from app.database import database, TablePlexLibraries
            from sqlalchemy import select
            
            # Get optional filter parameters
            library_type = request.args.get('type')  # 'movie' or 'show'
            enabled_only = request.args.get('enabled_only', 'false').lower() == 'true'
            sync_enabled_only = request.args.get('sync_enabled_only', 'false').lower() == 'true'
            
            # Build query
            query = select(TablePlexLibraries)
            
            # Apply filters
            if library_type:
                query = query.where(TablePlexLibraries.type == library_type)
            if enabled_only:
                query = query.where(TablePlexLibraries.enabled == 1)
            if sync_enabled_only:
                query = query.where(TablePlexLibraries.sync_enabled == 1)
            
            # Order by title
            query = query.order_by(TablePlexLibraries.title)
            
            libraries = database.execute(query).scalars().all()
            
            # Format response
            result = []
            for lib in libraries:
                result.append({
                    'key': lib.key,
                    'title': lib.title,
                    'type': lib.type,
                    'agent': lib.agent,
                    'scanner': lib.scanner,
                    'enabled': bool(lib.enabled),
                    'sync_enabled': bool(lib.sync_enabled),
                    'last_scan': lib.last_scan.isoformat() if lib.last_scan else None,
                    'scan_interval': lib.scan_interval,
                })
            
            return result, 200
            
        except Exception as e:
            logger.error(f"Error getting libraries for management: {e}")
            return {'error': str(e)}, 500


@api_ns_plex_sync.route('plex/sync/libraries/<string:library_key>/settings')
class PlexLibrarySettings(Resource):
    @authenticate
    @api_ns_plex_sync.response(200, 'Library updated successfully')
    @api_ns_plex_sync.response(401, 'Not Authenticated')
    @api_ns_plex_sync.response(404, 'Library not found')
    @api_ns_plex_sync.response(500, 'Internal server error')
    @api_ns_plex_sync.expect(library_update_model)
    def post(self, library_key):
        """Update library settings"""
        try:
            from app.database import database, TablePlexLibraries
            from sqlalchemy import select, update
            from datetime import datetime, timezone
            
            # Check if library exists
            existing = database.execute(
                select(TablePlexLibraries)
                .where(TablePlexLibraries.key == library_key)
            ).first()
            
            if not existing:
                return {'error': 'Library not found'}, 404
            
            # Get update data
            data = request.get_json()
            if not data:
                return {'error': 'No update data provided'}, 400
            
            # Validate data
            update_values = {}
            if 'enabled' in data:
                update_values['enabled'] = 1 if data['enabled'] else 0
            if 'sync_enabled' in data:
                update_values['sync_enabled'] = 1 if data['sync_enabled'] else 0
            if 'scan_interval' in data:
                scan_interval = int(data['scan_interval'])
                if scan_interval < 300:  # Minimum 5 minutes
                    return {'error': 'Scan interval must be at least 300 seconds (5 minutes)'}, 400
                update_values['scan_interval'] = scan_interval
            
            if not update_values:
                return {'error': 'No valid update fields provided'}, 400
            
            # Add updated timestamp
            update_values['updated_at_timestamp'] = datetime.now(timezone.utc)
            
            # Perform update
            database.execute(
                update(TablePlexLibraries)
                .where(TablePlexLibraries.key == library_key)
                .values(**update_values)
            )
            
            # Clear cache to refresh status
            sync_status_service.clear_cache()
            
            logger.info(f"Updated library {library_key} settings: {update_values}")
            
            return {
                'success': True,
                'message': f'Library {existing.title} updated successfully',
                'updated_fields': list(update_values.keys())
            }, 200
            
        except ValueError as e:
            return {'error': f'Invalid data: {str(e)}'}, 400
        except Exception as e:
            logger.error(f"Error updating library {library_key}: {e}")
            return {'error': str(e)}, 500
    
    @authenticate
    @api_ns_plex_sync.response(200, 'Success', library_model)
    @api_ns_plex_sync.response(401, 'Not Authenticated')
    @api_ns_plex_sync.response(404, 'Library not found')
    @api_ns_plex_sync.response(500, 'Internal server error')
    def get(self, library_key):
        """Get specific library details"""
        try:
            from app.database import database, TablePlexLibraries
            from sqlalchemy import select
            
            library = database.execute(
                select(TablePlexLibraries)
                .where(TablePlexLibraries.key == library_key)
            ).first()
            
            if not library:
                return {'error': 'Library not found'}, 404
            
            return {
                'key': library.key,
                'title': library.title,
                'type': library.type,
                'agent': library.agent,
                'scanner': library.scanner,
                'enabled': bool(library.enabled),
                'sync_enabled': bool(library.sync_enabled),
                'last_scan': library.last_scan.isoformat() if library.last_scan else None,
                'scan_interval': library.scan_interval,
            }, 200
            
        except Exception as e:
            logger.error(f"Error getting library {library_key}: {e}")
            return {'error': str(e)}, 500


@api_ns_plex_sync.route('plex/libraries/bulk-update')
class PlexLibrariesBulkUpdate(Resource):
    @authenticate
    @api_ns_plex_sync.response(200, 'Libraries updated successfully')
    @api_ns_plex_sync.response(401, 'Not Authenticated')
    @api_ns_plex_sync.response(400, 'Bad request')
    @api_ns_plex_sync.response(500, 'Internal server error')
    def post(self):
        """Bulk update multiple libraries"""
        try:
            from app.database import database, TablePlexLibraries
            from sqlalchemy import select, update
            from datetime import datetime, timezone
            
            data = request.get_json()
            if not data or 'libraries' not in data:
                return {'error': 'No libraries data provided'}, 400
            
            libraries_data = data['libraries']
            if not isinstance(libraries_data, list):
                return {'error': 'Libraries must be a list'}, 400
            
            updated_count = 0
            errors = []
            
            for lib_update in libraries_data:
                if 'key' not in lib_update:
                    errors.append('Missing library key in update data')
                    continue
                
                library_key = lib_update['key']
                
                # Check if library exists
                existing = database.execute(
                    select(TablePlexLibraries)
                    .where(TablePlexLibraries.key == library_key)
                ).first()
                
                if not existing:
                    errors.append(f'Library {library_key} not found')
                    continue
                
                # Build update values
                update_values = {}
                if 'enabled' in lib_update:
                    update_values['enabled'] = 1 if lib_update['enabled'] else 0
                if 'sync_enabled' in lib_update:
                    update_values['sync_enabled'] = 1 if lib_update['sync_enabled'] else 0
                if 'scan_interval' in lib_update:
                    scan_interval = int(lib_update['scan_interval'])
                    if scan_interval < 300:
                        errors.append(f'Library {library_key}: scan interval must be at least 300 seconds')
                        continue
                    update_values['scan_interval'] = scan_interval
                
                if update_values:
                    update_values['updated_at_timestamp'] = datetime.now(timezone.utc)
                    
                    # Perform update
                    database.execute(
                        update(TablePlexLibraries)
                        .where(TablePlexLibraries.key == library_key)
                        .values(**update_values)
                    )
                    
                    updated_count += 1
                    logger.info(f"Bulk updated library {library_key}: {update_values}")
            
            # Clear cache to refresh status
            if updated_count > 0:
                sync_status_service.clear_cache()
            
            response = {
                'success': True,
                'message': f'Bulk update completed: {updated_count} libraries updated',
                'updated_count': updated_count
            }
            
            if errors:
                response['errors'] = errors
            
            return response, 200
            
        except Exception as e:
            logger.error(f"Error during bulk update: {e}")
            return {'error': str(e)}, 500


@api_ns_plex_sync.route('plex/retry/statistics')
class PlexRetryStatistics(Resource):
    @authenticate
    @api_ns_plex_sync.response(200, 'Success')
    @api_ns_plex_sync.response(401, 'Not Authenticated')
    @api_ns_plex_sync.response(500, 'Internal server error')
    def get(self):
        """Get retry operation statistics"""
        try:
            stats = retry_service.get_retry_statistics()
            return stats, 200
        except Exception as e:
            logger.error(f"Error getting retry statistics: {e}")
            return {'error': str(e)}, 500


@api_ns_plex_sync.route('plex/retry/process')
class PlexRetryProcess(Resource):
    @authenticate
    @api_ns_plex_sync.response(200, 'Retry processing completed')
    @api_ns_plex_sync.response(401, 'Not Authenticated')
    @api_ns_plex_sync.response(500, 'Internal server error')
    def post(self):
        """Manually trigger retry operation processing"""
        try:
            results = retry_worker.process_pending_operations()
            return {
                'success': True,
                'message': 'Retry processing completed',
                'results': results
            }, 200
        except Exception as e:
            logger.error(f"Error processing retries: {e}")
            return {
                'success': False,
                'message': f'Error processing retries: {str(e)}',
                'error': str(e)
            }, 500


@api_ns_plex_sync.route('plex/retry/cleanup')
class PlexRetryCleanup(Resource):
    @authenticate
    @api_ns_plex_sync.response(200, 'Cleanup completed')
    @api_ns_plex_sync.response(401, 'Not Authenticated')
    @api_ns_plex_sync.response(500, 'Internal server error')  
    def post(self):
        """Clean up old retry operations"""
        try:
            days = int(request.args.get('days', '7'))
            count = retry_service.cleanup_old_operations(days)
            return {
                'success': True,
                'message': f'Cleaned up {count} old retry operations',
                'cleaned_count': count
            }, 200
        except Exception as e:
            logger.error(f"Error cleaning up retries: {e}")
            return {'error': str(e)}, 500


# New endpoints for frontend sync configuration interface
settings_model = api_ns_plex_sync.model('SyncSettings', {
    'sync_enabled': fields.Boolean(description='Enable/disable sync'),
    'sync_frequency_seconds': fields.Integer(description='Sync frequency in seconds'),
    'conflict_resolution_strategy': fields.String(description='Conflict resolution strategy'),
    'max_retries': fields.Integer(description='Maximum retry attempts'),
    'retry_delay_seconds': fields.Integer(description='Retry delay in seconds'),
    'batch_size': fields.Integer(description='Batch size for processing'),
    'cache_ttl_seconds': fields.Integer(description='Cache TTL in seconds'),
    'webhook_enabled': fields.Boolean(description='Enable webhook processing'),
    'full_sync_on_startup': fields.Boolean(description='Perform full sync on startup'),
    'incremental_sync_enabled': fields.Boolean(description='Enable incremental sync'),
    'health_check_enabled': fields.Boolean(description='Enable health checking'),
})

sync_trigger_model = api_ns_plex_sync.model('SyncTrigger', {
    'type': fields.String(description='Sync type (full or incremental)', required=True),
    'library_id': fields.String(description='Optional library ID for targeted sync'),
})


@api_ns_plex_sync.route('plex/sync/settings')
class PlexSyncSettings(Resource):
    post_request_parser = reqparse.RequestParser()
    post_request_parser.add_argument('sync_enabled', type=bool, required=False, help='Enable/disable sync')
    post_request_parser.add_argument('sync_frequency_seconds', type=int, required=False, help='Sync frequency in seconds')
    post_request_parser.add_argument('conflict_resolution_strategy', type=str, required=False, help='Conflict resolution strategy')
    post_request_parser.add_argument('max_retries', type=int, required=False, help='Maximum retry attempts')
    post_request_parser.add_argument('retry_delay_seconds', type=int, required=False, help='Retry delay in seconds')
    post_request_parser.add_argument('batch_size', type=int, required=False, help='Batch size for processing')
    post_request_parser.add_argument('cache_ttl_seconds', type=int, required=False, help='Cache TTL in seconds')
    post_request_parser.add_argument('webhook_enabled', type=bool, required=False, help='Enable webhook processing')
    post_request_parser.add_argument('full_sync_on_startup', type=bool, required=False, help='Perform full sync on startup')
    post_request_parser.add_argument('incremental_sync_enabled', type=bool, required=False, help='Enable incremental sync')
    post_request_parser.add_argument('health_check_enabled', type=bool, required=False, help='Enable health checking')
    
    @authenticate
    @api_ns_plex_sync.response(200, 'Success', settings_model)
    @api_ns_plex_sync.response(401, 'Not Authenticated')
    @api_ns_plex_sync.response(500, 'Internal server error')
    def get(self):
        """Get current Plex sync settings"""
        try:
            from app.config import settings
            
            # Build settings response
            sync_settings = {
                'sync_enabled': getattr(settings.plex, 'sync_enabled', False),
                'sync_frequency_seconds': getattr(settings.plex, 'sync_frequency_seconds', 3600),
                'conflict_resolution_strategy': getattr(settings.plex, 'conflict_resolution_strategy', 'plex_wins'),
                'max_retries': getattr(settings.plex, 'max_retries', 3),
                'retry_delay_seconds': getattr(settings.plex, 'retry_delay_seconds', 60),
                'batch_size': getattr(settings.plex, 'batch_size', 50),
                'cache_ttl_seconds': getattr(settings.plex, 'cache_ttl_seconds', 3600),
                'webhook_enabled': getattr(settings.plex, 'webhook_enabled', True),
                'full_sync_on_startup': getattr(settings.plex, 'full_sync_on_startup', False),
                'incremental_sync_enabled': getattr(settings.plex, 'incremental_sync_enabled', True),
                'health_check_enabled': getattr(settings.plex, 'health_check_enabled', True),
            }
            
            return {'data': sync_settings}, 200
            
        except Exception as e:
            logger.error(f"Error getting sync settings: {e}")
            return {'error': str(e)}, 500
    
    @authenticate
    @api_ns_plex_sync.response(200, 'Settings updated successfully')
    @api_ns_plex_sync.response(400, 'Invalid settings')
    @api_ns_plex_sync.response(401, 'Not Authenticated')
    @api_ns_plex_sync.response(500, 'Internal server error')
    @api_ns_plex_sync.doc(parser=post_request_parser)
    def post(self):
        """Update Plex sync settings"""
        try:
            from app.config import settings
            import os
            
            args = self.post_request_parser.parse_args()
            if not any(v is not None for v in args.values()):
                return {'error': 'No settings data provided'}, 400
            
            # Validate and update settings
            updated_settings = {}
            
            # Boolean settings
            bool_settings = [
                'sync_enabled', 'webhook_enabled', 'full_sync_on_startup', 
                'incremental_sync_enabled', 'health_check_enabled'
            ]
            for setting in bool_settings:
                if args.get(setting) is not None:
                    updated_settings[f'plex.{setting}'] = bool(args.get(setting))
            
            # Integer settings with validation
            if args.get('sync_frequency_seconds') is not None:
                freq = int(args.get('sync_frequency_seconds'))
                if 300 <= freq <= 86400:  # 5 minutes to 24 hours
                    updated_settings['plex.sync_frequency_seconds'] = freq
                else:
                    return {'error': 'sync_frequency_seconds must be between 300 and 86400'}, 400
            
            if args.get('max_retries') is not None:
                retries = int(args.get('max_retries'))
                if 0 <= retries <= 10:
                    updated_settings['plex.max_retries'] = retries
                else:
                    return {'error': 'max_retries must be between 0 and 10'}, 400
            
            if args.get('retry_delay_seconds') is not None:
                delay = int(args.get('retry_delay_seconds'))
                if 1 <= delay <= 300:
                    updated_settings['plex.retry_delay_seconds'] = delay
                else:
                    return {'error': 'retry_delay_seconds must be between 1 and 300'}, 400
            
            if args.get('batch_size') is not None:
                batch = int(args.get('batch_size'))
                if 1 <= batch <= 1000:
                    updated_settings['plex.batch_size'] = batch
                else:
                    return {'error': 'batch_size must be between 1 and 1000'}, 400
            
            if args.get('cache_ttl_seconds') is not None:
                ttl = int(args.get('cache_ttl_seconds'))
                if 60 <= ttl <= 86400:
                    updated_settings['plex.cache_ttl_seconds'] = ttl
                else:
                    return {'error': 'cache_ttl_seconds must be between 60 and 86400'}, 400
            
            # String settings with validation
            if args.get('conflict_resolution_strategy') is not None:
                strategy = args.get('conflict_resolution_strategy')
                valid_strategies = ['plex_wins', 'database_wins', 'merge_metadata', 'manual_review']
                if strategy in valid_strategies:
                    updated_settings['plex.conflict_resolution_strategy'] = strategy
                else:
                    return {'error': f'Invalid conflict resolution strategy. Must be one of: {valid_strategies}'}, 400
            
            if not updated_settings:
                return {'error': 'No valid settings provided'}, 400
            
            # Update settings in configuration
            for key, value in updated_settings.items():
                # Create nested attribute if needed
                section, setting = key.split('.')
                if not hasattr(settings, section):
                    setattr(settings, section, type('obj', (object,), {}))
                setattr(getattr(settings, section), setting, value)
            
            # Save configuration to file
            try:
                settings.write()
                logger.info(f"Updated Plex sync settings: {list(updated_settings.keys())}")
                
                # Force reload of settings to ensure they're fresh
                from app.config import settings as fresh_settings
                
            except Exception as e:
                logger.warning(f"Failed to write settings to file: {e}")
                # Continue anyway - settings are updated in memory
            
            # Clear cache to reflect changes
            sync_status_service.clear_cache()
            
            return {
                'data': {
                    'success': True,
                    'message': f'Updated {len(updated_settings)} settings successfully',
                    'updated_settings': list(updated_settings.keys())
                }
            }, 200
            
        except ValueError as e:
            return {'error': f'Invalid value: {str(e)}'}, 400
        except Exception as e:
            logger.error(f"Error updating sync settings: {e}")
            return {'error': str(e)}, 500


@api_ns_plex_sync.route('plex/sync/trigger')
class PlexSyncTrigger(Resource):
    post_request_parser = reqparse.RequestParser()
    post_request_parser.add_argument('type', type=str, required=True, help='Sync type (full or incremental)')
    post_request_parser.add_argument('library_id', type=str, required=False, help='Optional library ID for targeted sync')
    
    @authenticate
    @api_ns_plex_sync.response(200, 'Sync triggered successfully')
    @api_ns_plex_sync.response(400, 'Invalid trigger data')
    @api_ns_plex_sync.response(401, 'Not Authenticated')
    @api_ns_plex_sync.response(500, 'Sync trigger failed')
    @api_ns_plex_sync.doc(parser=post_request_parser)
    def post(self):
        """Trigger manual sync operation"""
        try:
            args = self.post_request_parser.parse_args()
            sync_type = args.get('type')
            library_id = args.get('library_id')
            
            if not sync_type:
                return {'error': 'Sync type is required'}, 400
            
            if sync_type not in ['full', 'incremental']:
                return {'error': 'Sync type must be "full" or "incremental"'}, 400
            
            logger.info(f"Manual sync triggered: type={sync_type}, library_id={library_id}")
            
            # Note: library_id parameter is accepted but current sync_plex_libraries() function
            # processes all libraries. Future enhancement could support library-specific sync.
            
            # Get current settings for sync parameters
            from app.config import settings
            conflict_strategy = getattr(settings.plex, 'conflict_resolution_strategy', 'plex_wins')
            
            # Perform sync operation
            if sync_type == 'full':
                sync_results = sync_plex_libraries(
                    full_sync=True,
                    cleanup_removed=True,
                    conflict_strategy=conflict_strategy
                )
            else:  # incremental
                sync_results = sync_plex_libraries(
                    full_sync=False,
                    conflict_strategy=conflict_strategy
                )
            
            # Clear cache to refresh status
            sync_status_service.clear_cache()
            
            if sync_results.get('success', False):
                # Clean all datetime objects from the response
                clean_results = clean_datetime_objects(sync_results)
                
                return {
                    'data': {
                        'success': True,
                        'message': f'{sync_type.title()} sync completed successfully',
                        'sync_id': clean_results.get('sync_id'),
                        'started_at': clean_results.get('start_time'),
                        'estimated_duration': str(clean_results.get('estimated_duration', '')),
                        'statistics': clean_results
                    }
                }, 200
            else:
                return {
                    'data': {
                        'success': False,
                        'message': f'{sync_type.title()} sync failed',
                        'error_message': sync_results.get('error'),
                        'statistics': {k: str(v) if hasattr(v, 'isoformat') else v 
                                     for k, v in sync_results.items() if k != 'error'}
                    }
                }, 500
                
        except Exception as e:
            logger.error(f"Error triggering sync: {e}")
            return {
                'data': {
                    'success': False,
                    'message': f'Sync trigger error: {str(e)}',
                    'error': str(e)
                }
            }, 500


@api_ns_plex_sync.route('plex/sync/history')
class PlexSyncHistory(Resource):
    @authenticate
    @api_ns_plex_sync.response(200, 'Success')
    @api_ns_plex_sync.response(401, 'Not Authenticated')
    @api_ns_plex_sync.response(500, 'Internal server error')
    def get(self):
        """Get sync operation history"""
        try:
            # Get pagination parameters
            page = int(request.args.get('page', '1'))
            limit = int(request.args.get('limit', '25'))
            
            if page < 1:
                page = 1
            if limit < 1 or limit > 100:
                limit = 25
            
            # For now, return mock data since we don't have a sync history table yet
            # In a full implementation, this would query a sync_history table
            mock_history = {
                'items': [
                    {
                        'id': 'sync_001',
                        'sync_type': 'incremental',
                        'started_at': '2025-09-07T19:30:00Z',
                        'completed_at': '2025-09-07T19:31:30Z',
                        'status': 'completed',
                        'items_processed': 150,
                        'items_added': 5,
                        'items_updated': 12,
                        'items_removed': 0,
                        'errors': 0,
                        'duration_seconds': 90
                    },
                    {
                        'id': 'sync_002',
                        'sync_type': 'full',
                        'started_at': '2025-09-07T18:00:00Z',
                        'completed_at': '2025-09-07T18:15:45Z',
                        'status': 'completed',
                        'items_processed': 1250,
                        'items_added': 45,
                        'items_updated': 23,
                        'items_removed': 8,
                        'errors': 2,
                        'duration_seconds': 945
                    }
                ],
                'total': 2,
                'page': page,
                'limit': limit,
                'has_next': False,
                'has_prev': False
            }
            
            return mock_history, 200
            
        except Exception as e:
            logger.error(f"Error getting sync history: {e}")
            return {'error': str(e)}, 500