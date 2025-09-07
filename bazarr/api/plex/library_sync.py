# coding=utf-8

from flask import jsonify, request
from flask_restx import Resource, Namespace, fields

from app.database import database
from app.config import settings
from plex.sync import sync_plex_libraries, get_library_sync_status

from ..utils import authenticate

api_ns_plex_library = Namespace('Plex Library Sync', description='Manage Plex library synchronization')


# Define models for Swagger documentation
sync_request_model = api_ns_plex_library.model('SyncRequest', {
    'full_sync': fields.Boolean(default=True, description='Perform full sync if True, incremental if False'),
    'cleanup_removed': fields.Boolean(default=True, description='Remove libraries that no longer exist in Plex')
})

sync_response_model = api_ns_plex_library.model('SyncResponse', {
    'success': fields.Boolean(description='Whether sync completed successfully'),
    'libraries_processed': fields.Integer(description='Number of libraries processed'),
    'libraries_added': fields.Integer(description='Number of new libraries added'),
    'libraries_updated': fields.Integer(description='Number of existing libraries updated'),
    'duration_seconds': fields.Float(description='Time taken for sync in seconds'),
    'errors': fields.List(fields.String, description='List of error messages if any')
})

library_model = api_ns_plex_library.model('Library', {
    'key': fields.String(description='Plex library key'),
    'title': fields.String(description='Library title'),
    'type': fields.String(description='Library type (movie/show)'),
    'enabled': fields.Boolean(description='Whether library is enabled'),
    'sync_enabled': fields.Boolean(description='Whether sync is enabled for this library'),
    'last_scan': fields.String(description='ISO timestamp of last scan')
})

status_response_model = api_ns_plex_library.model('StatusResponse', {
    'total_libraries': fields.Integer(description='Total number of libraries'),
    'movie_libraries': fields.Integer(description='Number of movie libraries'),
    'show_libraries': fields.Integer(description='Number of TV show libraries'),
    'enabled_libraries': fields.Integer(description='Number of enabled libraries'),
    'last_sync': fields.String(description='ISO timestamp of most recent sync'),
    'libraries': fields.List(fields.Nested(library_model), description='List of all libraries')
})


@api_ns_plex_library.route('/libraries/sync')
class PlexLibrarySync(Resource):
    """Trigger Plex library synchronization"""
    
    @authenticate
    @api_ns_plex_library.doc(
        description='Trigger synchronization of Plex libraries',
        responses={
            200: 'Sync completed successfully',
            400: 'Bad request',
            401: 'Unauthorized',
            500: 'Internal server error'
        }
    )
    @api_ns_plex_library.expect(sync_request_model)
    @api_ns_plex_library.marshal_with(sync_response_model, code=200)
    def post(self):
        """Trigger Plex library synchronization"""
        args = request.get_json() or {}
        
        # Get parameters from request
        full_sync = args.get('full_sync', True)
        cleanup_removed = args.get('cleanup_removed', True)
        
        # Perform synchronization
        result = sync_plex_libraries(full_sync=full_sync, cleanup_removed=cleanup_removed)
        
        # Return results
        if result.get('success'):
            return result, 200
        else:
            return result, 500


@api_ns_plex_library.route('/libraries/status')
class PlexLibraryStatus(Resource):
    """Get Plex library sync status"""
    
    @authenticate
    @api_ns_plex_library.doc(
        description='Get current status of Plex library synchronization',
        responses={
            200: 'Status retrieved successfully',
            401: 'Unauthorized',
            500: 'Internal server error'
        }
    )
    @api_ns_plex_library.marshal_with(status_response_model, code=200)
    def get(self):
        """Get Plex library sync status"""
        try:
            status = get_library_sync_status()
            
            if 'error' in status:
                return {'error': status['error']}, 500
            
            return status, 200
            
        except Exception as e:
            return {'error': str(e)}, 500


@api_ns_plex_library.route('/libraries')
class PlexLibrariesList(Resource):
    """List all Plex libraries"""
    
    @authenticate
    @api_ns_plex_library.doc(
        description='Get list of all Plex libraries',
        responses={
            200: 'Libraries retrieved successfully',
            401: 'Unauthorized',
            500: 'Internal server error'
        }
    )
    @api_ns_plex_library.marshal_with(library_model, as_list=True, code=200)
    def get(self):
        """Get list of all Plex libraries"""
        try:
            status = get_library_sync_status()
            
            if 'error' in status:
                return {'error': status['error']}, 500
            
            return status.get('libraries', []), 200
            
        except Exception as e:
            return {'error': str(e)}, 500