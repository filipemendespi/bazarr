# coding=utf-8

"""
Plex Subtitle API Endpoints

RESTful API endpoints for Plex subtitle integration, providing subtitle download,
search, and management capabilities for Plex content.
"""

import logging
from flask import request
from flask_restx import Resource, Namespace, reqparse, fields
from operator import itemgetter

from api.utils import authenticate
from plex.subtitle_integration import (
    download_plex_movie_subtitles,
    download_plex_episode_subtitles, 
    search_plex_subtitles,
    bulk_download_plex_library
)

logger = logging.getLogger(__name__)

# Create API namespace
api_ns_plex_subtitles = Namespace('Plex Subtitles', description='Plex subtitle operations')


# ===== MODELS FOR SWAGGER DOCUMENTATION =====

subtitle_download_model = api_ns_plex_subtitles.model('SubtitleDownloadRequest', {
    'plex_id': fields.Integer(required=True, description='Plex media ID'),
    'media_type': fields.String(required=True, description='Media type: movie or episode'),
    'providers': fields.List(fields.String(), description='Specific providers to use'),
    'languages': fields.List(fields.String(), description='Languages to download'),
    'hi': fields.Boolean(default=False, description='Hearing impaired subtitles'),
    'forced': fields.Boolean(default=False, description='Forced subtitles only')
})

subtitle_search_model = api_ns_plex_subtitles.model('SubtitleSearchRequest', {
    'plex_id': fields.Integer(required=True, description='Plex media ID'),
    'media_type': fields.String(required=True, description='Media type: movie or episode'),
    'audio_language': fields.String(description='Audio language code'),
    'providers': fields.List(fields.String(), description='Providers to search'),
    'hi': fields.Boolean(default=False, description='Include hearing impaired'),
    'forced': fields.Boolean(default=False, description='Include forced subtitles')
})

bulk_download_model = api_ns_plex_subtitles.model('BulkDownloadRequest', {
    'library_key': fields.String(required=True, description='Plex library key'),
    'content_type': fields.String(description='Filter by content type: movies, series, or all'),
    'languages': fields.List(fields.String(), description='Languages to download'),
    'missing_only': fields.Boolean(default=True, description='Only download missing subtitles')
})


# ===== SUBTITLE DOWNLOAD ENDPOINTS =====

@api_ns_plex_subtitles.route('plex/subtitles/download')
class PlexSubtitleDownload(Resource):
    """Download subtitles for individual Plex content."""
    
    download_parser = reqparse.RequestParser()
    download_parser.add_argument('plex_id', type=int, required=True, help='Plex media ID')
    download_parser.add_argument('media_type', type=str, required=True, choices=['movie', 'episode'], 
                               help='Media type')
    download_parser.add_argument('providers', type=str, action='append', help='Subtitle providers')
    download_parser.add_argument('languages', type=str, action='append', help='Subtitle languages')
    download_parser.add_argument('hi', type=bool, default=False, help='Hearing impaired subtitles')
    download_parser.add_argument('forced', type=bool, default=False, help='Forced subtitles only')

    @authenticate
    @api_ns_plex_subtitles.response(200, 'Subtitles downloaded successfully')
    @api_ns_plex_subtitles.response(400, 'Invalid request parameters')
    @api_ns_plex_subtitles.response(404, 'Plex content not found')
    @api_ns_plex_subtitles.response(500, 'Subtitle download failed')
    @api_ns_plex_subtitles.doc(parser=download_parser)
    def post(self):
        """Download subtitles for a specific Plex movie or episode"""
        try:
            args = self.download_parser.parse_args()
            plex_id = args.get('plex_id')
            media_type = args.get('media_type')
            
            logger.info(f"Starting subtitle download for Plex {media_type} ID: {plex_id}")
            
            # Prepare download parameters
            download_params = {}
            if args.get('providers'):
                download_params['providers'] = args.get('providers')
            if args.get('languages'):
                download_params['languages'] = args.get('languages')
            if args.get('hi'):
                download_params['hi'] = args.get('hi')
            if args.get('forced'):
                download_params['forced'] = args.get('forced')
            
            # Call appropriate download function
            if media_type == 'movie':
                result = download_plex_movie_subtitles(plex_id, **download_params)
            elif media_type == 'episode':
                result = download_plex_episode_subtitles(plex_id, **download_params)
            else:
                return {'error': f'Invalid media type: {media_type}'}, 400
            
            if result.get('success'):
                return {
                    'message': f'Subtitles downloaded successfully for {media_type} {plex_id}',
                    'plex_id': plex_id,
                    'media_type': media_type,
                    'result': result.get('result')
                }, 200
            else:
                return {
                    'error': f'Failed to download subtitles: {result.get("error")}',
                    'plex_id': plex_id,
                    'media_type': media_type
                }, 500
                
        except Exception as e:
            logger.error(f"Subtitle download API error: {e}")
            return {'error': f'Internal server error: {str(e)}'}, 500


# ===== SUBTITLE SEARCH ENDPOINTS =====

@api_ns_plex_subtitles.route('plex/subtitles/search')
class PlexSubtitleSearch(Resource):
    """Search available subtitles for Plex content."""
    
    search_parser = reqparse.RequestParser()
    search_parser.add_argument('plex_id', type=int, required=True, help='Plex media ID')
    search_parser.add_argument('media_type', type=str, required=True, choices=['movie', 'episode'],
                             help='Media type')
    search_parser.add_argument('audio_language', type=str, help='Audio language code')
    search_parser.add_argument('providers', type=str, action='append', help='Providers to search')
    search_parser.add_argument('hi', type=bool, default=False, help='Include hearing impaired')
    search_parser.add_argument('forced', type=bool, default=False, help='Include forced subtitles')

    @authenticate
    @api_ns_plex_subtitles.response(200, 'Subtitle search completed')
    @api_ns_plex_subtitles.response(400, 'Invalid search parameters')
    @api_ns_plex_subtitles.response(404, 'Plex content not found')
    @api_ns_plex_subtitles.response(500, 'Subtitle search failed')
    @api_ns_plex_subtitles.doc(parser=search_parser)
    def post(self):
        """Search for available subtitles for a specific Plex movie or episode"""
        try:
            args = self.search_parser.parse_args()
            plex_id = args.get('plex_id')
            media_type = args.get('media_type')
            
            logger.info(f"Starting subtitle search for Plex {media_type} ID: {plex_id}")
            
            # Prepare search parameters
            search_params = {}
            if args.get('audio_language'):
                search_params['audio_language'] = args.get('audio_language')
            if args.get('providers'):
                search_params['providers'] = args.get('providers')
            if args.get('hi'):
                search_params['hi'] = args.get('hi')
            if args.get('forced'):
                search_params['forced'] = args.get('forced')
            
            # Perform search
            result = search_plex_subtitles(plex_id, media_type, **search_params)
            
            if result.get('success'):
                return {
                    'message': f'Subtitle search completed for {media_type} {plex_id}',
                    'plex_id': plex_id,
                    'media_type': media_type,
                    'subtitles': result.get('subtitles', []),
                    'count': len(result.get('subtitles', []))
                }, 200
            else:
                return {
                    'error': f'Subtitle search failed: {result.get("error")}',
                    'plex_id': plex_id,
                    'media_type': media_type
                }, 500
                
        except Exception as e:
            logger.error(f"Subtitle search API error: {e}")
            return {'error': f'Internal server error: {str(e)}'}, 500


@api_ns_plex_subtitles.route('plex/subtitles/manual-download')
class PlexManualSubtitleDownload(Resource):
    """Download a specific subtitle from manual search results."""
    
    manual_download_parser = reqparse.RequestParser()
    manual_download_parser.add_argument('plex_id', type=int, required=True, help='Plex media ID')
    manual_download_parser.add_argument('media_type', type=str, required=True, choices=['movie', 'episode'],
                                       help='Media type')
    manual_download_parser.add_argument('subtitle_data', type=str, required=True, 
                                       help='Base64 encoded subtitle object from search results')
    manual_download_parser.add_argument('provider', type=str, required=True, help='Provider name')
    manual_download_parser.add_argument('audio_language', type=str, help='Audio language code')
    manual_download_parser.add_argument('hi', type=str, default='False', help='Hearing impaired flag')
    manual_download_parser.add_argument('forced', type=str, default='False', help='Forced flag')
    manual_download_parser.add_argument('use_original_format', type=bool, default=False,
                                       help='Use original subtitle format')

    @authenticate
    @api_ns_plex_subtitles.response(200, 'Manual subtitle downloaded successfully')
    @api_ns_plex_subtitles.response(400, 'Invalid manual download request')
    @api_ns_plex_subtitles.response(404, 'Plex content not found')
    @api_ns_plex_subtitles.response(500, 'Manual download failed')
    @api_ns_plex_subtitles.doc(parser=manual_download_parser)
    def post(self):
        """Download a specific subtitle selected from manual search results"""
        try:
            from plex.subtitle_integration import download_plex_manual_subtitle
            
            args = self.manual_download_parser.parse_args()
            plex_id = args.get('plex_id')
            media_type = args.get('media_type')
            subtitle_data = args.get('subtitle_data')
            provider = args.get('provider')
            
            logger.info(f"Manual subtitle download for Plex {media_type} {plex_id} from {provider}")
            
            # Prepare download parameters
            download_params = {}
            if args.get('audio_language'):
                download_params['audio_language'] = args.get('audio_language')
            if args.get('hi'):
                download_params['hi'] = args.get('hi')
            if args.get('forced'):
                download_params['forced'] = args.get('forced')
            if args.get('use_original_format'):
                download_params['use_original_format'] = args.get('use_original_format')
            
            result = download_plex_manual_subtitle(plex_id, media_type, subtitle_data, provider, **download_params)
            
            if result.get('success'):
                return {
                    'message': f'Subtitle downloaded successfully for {media_type} {plex_id}',
                    'plex_id': plex_id,
                    'media_type': media_type,
                    'provider': provider,
                    'result': result.get('result')
                }, 200
            else:
                return {
                    'error': f'Failed to download subtitle: {result.get("error")}',
                    'plex_id': plex_id,
                    'media_type': media_type,
                    'provider': provider
                }, 500
                
        except Exception as e:
            logger.error(f"Manual subtitle download API error: {e}")
            return {'error': f'Internal server error: {str(e)}'}, 500


# ===== BULK OPERATIONS =====

@api_ns_plex_subtitles.route('plex/subtitles/bulk-download')
class PlexBulkSubtitleDownload(Resource):
    """Bulk download subtitles for entire Plex libraries."""
    
    bulk_parser = reqparse.RequestParser()
    bulk_parser.add_argument('library_key', type=str, required=True, help='Plex library key')
    bulk_parser.add_argument('content_type', type=str, choices=['movies', 'series', 'all'], 
                           default='all', help='Content type filter')
    bulk_parser.add_argument('languages', type=str, action='append', help='Languages to download')
    bulk_parser.add_argument('missing_only', type=bool, default=True, 
                           help='Only download missing subtitles')
    bulk_parser.add_argument('dry_run', type=bool, default=False, 
                           help='Preview what would be downloaded')

    @authenticate
    @api_ns_plex_subtitles.response(200, 'Bulk download completed')
    @api_ns_plex_subtitles.response(400, 'Invalid bulk request')
    @api_ns_plex_subtitles.response(500, 'Bulk download failed')
    @api_ns_plex_subtitles.doc(parser=bulk_parser)
    def post(self):
        """Download subtitles for all content in a Plex library"""
        try:
            args = self.bulk_parser.parse_args()
            library_key = args.get('library_key')
            
            logger.info(f"Starting bulk subtitle download for library: {library_key}")
            
            if args.get('dry_run'):
                # TODO: Implement dry run preview
                return {
                    'message': 'Dry run mode - preview of what would be downloaded',
                    'library_key': library_key,
                    'note': 'Dry run functionality not yet implemented'
                }, 200
            
            # Perform bulk download
            result = bulk_download_plex_library(library_key)
            
            if result.get('success'):
                return {
                    'message': f'Bulk download completed for library {library_key}',
                    'library_key': library_key,
                    'processed_count': result.get('processed', 0),
                    'results': result.get('results')
                }, 200
            else:
                return {
                    'error': f'Bulk download failed: {result.get("error")}',
                    'library_key': library_key
                }, 500
                
        except Exception as e:
            logger.error(f"Bulk download API error: {e}")
            return {'error': f'Internal server error: {str(e)}'}, 500


# ===== SUBTITLE STATUS ENDPOINTS =====

@api_ns_plex_subtitles.route('plex/subtitles/status/<int:plex_id>')
class PlexSubtitleStatus(Resource):
    """Get subtitle status for Plex content."""

    @authenticate
    @api_ns_plex_subtitles.response(200, 'Subtitle status retrieved')
    @api_ns_plex_subtitles.response(404, 'Plex content not found')
    @api_ns_plex_subtitles.response(500, 'Failed to get subtitle status')
    def get(self, plex_id):
        """Get current subtitle status for a Plex movie or episode"""
        try:
            # TODO: Implement subtitle status checking
            # This would check current subtitle files, missing languages, etc.
            
            logger.info(f"Getting subtitle status for Plex ID: {plex_id}")
            
            return {
                'plex_id': plex_id,
                'status': 'not_implemented',
                'message': 'Subtitle status checking not yet implemented',
                'subtitles': [],
                'missing': [],
                'note': 'This endpoint will show current subtitles and missing languages'
            }, 200
            
        except Exception as e:
            logger.error(f"Subtitle status API error: {e}")
            return {'error': f'Internal server error: {str(e)}'}, 500


# ===== SUBTITLE HISTORY =====

@api_ns_plex_subtitles.route('plex/subtitles/history/<int:plex_id>')
class PlexSubtitleHistory(Resource):
    """Get subtitle download history for Plex content."""

    @authenticate
    @api_ns_plex_subtitles.response(200, 'Subtitle history retrieved')
    @api_ns_plex_subtitles.response(404, 'Plex content not found')
    @api_ns_plex_subtitles.response(500, 'Failed to get subtitle history')
    def get(self, plex_id):
        """Get subtitle download history for a Plex movie or episode"""
        try:
            # TODO: Implement subtitle history retrieval
            # This would show past downloads, upgrades, failures, etc.
            
            logger.info(f"Getting subtitle history for Plex ID: {plex_id}")
            
            return {
                'plex_id': plex_id,
                'history': [],
                'message': 'Subtitle history tracking not yet implemented',
                'note': 'This endpoint will show download history, upgrades, and failures'
            }, 200
            
        except Exception as e:
            logger.error(f"Subtitle history API error: {e}")
            return {'error': f'Internal server error: {str(e)}'}, 500