# coding=utf-8

from flask_restx import Resource, Namespace, reqparse, fields, marshal

from app.database import TableMovies, TablePlexMovies, database, update, select, func
from radarr.sync.movies import update_one_movie
from subtitles.indexer.movies import list_missing_subtitles_movies, movies_scan_subtitles
from app.event_handler import event_stream
from subtitles.wanted import wanted_search_missing_subtitles_movies
from subtitles.mass_download import movies_download_subtitles
from api.swaggerui import subtitles_model, subtitles_language_model, audio_language_model

from api.utils import authenticate, None_Keys, postprocess
from app.config import settings

api_ns_movies = Namespace('Movies', description='List movies metadata, update movie languages profile or run actions '
                                                'for specific movies.')


@api_ns_movies.route('movies')
class Movies(Resource):
    get_request_parser = reqparse.RequestParser()
    get_request_parser.add_argument('start', type=int, required=False, default=0, help='Paging start integer')
    get_request_parser.add_argument('length', type=int, required=False, default=-1, help='Paging length integer')
    get_request_parser.add_argument('radarrid[]', type=int, action='append', required=False, default=[],
                                    help='Movies IDs to get metadata for')

    get_subtitles_model = api_ns_movies.model('subtitles_model', subtitles_model)
    get_subtitles_language_model = api_ns_movies.model('subtitles_language_model', subtitles_language_model)
    get_audio_language_model = api_ns_movies.model('audio_language_model', audio_language_model)

    data_model = api_ns_movies.model('movies_data_model', {
        'alternativeTitles': fields.List(fields.String),
        'audio_language': fields.Nested(get_audio_language_model),
        'fanart': fields.String(),
        'imdbId': fields.String(),
        'missing_subtitles': fields.Nested(get_subtitles_language_model),
        'monitored': fields.Boolean(),
        'overview': fields.String(),
        'path': fields.String(),
        'poster': fields.String(),
        'profileId': fields.Integer(),
        'radarrId': fields.Integer(),
        'sceneName': fields.String(),
        'subtitles': fields.Nested(get_subtitles_model),
        'tags': fields.List(fields.String),
        'title': fields.String(),
        'year': fields.String(),
    })

    get_response_model = api_ns_movies.model('MoviesGetResponse', {
        'data': fields.Nested(data_model),
        'total': fields.Integer(),
    })

    @authenticate
    @api_ns_movies.doc(parser=get_request_parser)
    @api_ns_movies.response(200, 'Success')
    @api_ns_movies.response(401, 'Not Authenticated')
    def get(self):
        """List movies metadata for specific movies"""
        args = self.get_request_parser.parse_args()
        start = args.get('start')
        length = args.get('length')
        radarrId = args.get('radarrid[]')

        stmt = select(TableMovies.alternativeTitles,
                      TableMovies.audio_language,
                      TableMovies.fanart,
                      TableMovies.imdbId,
                      TableMovies.missing_subtitles,
                      TableMovies.monitored,
                      TableMovies.overview,
                      TableMovies.path,
                      TableMovies.poster,
                      TableMovies.profileId,
                      TableMovies.radarrId,
                      TableMovies.sceneName,
                      TableMovies.subtitles,
                      TableMovies.tags,
                      TableMovies.title,
                      TableMovies.year,
                      )\
            .order_by(TableMovies.sortTitle)

        if len(radarrId) != 0:
            stmt = stmt.where(TableMovies.radarrId.in_(radarrId))

        if length > 0:
            stmt = stmt.limit(length).offset(start)

        results = [postprocess({
            'alternativeTitles': x.alternativeTitles,
            'audio_language': x.audio_language,
            'fanart': x.fanart,
            'imdbId': x.imdbId,
            'missing_subtitles': x.missing_subtitles,
            'monitored': x.monitored,
            'overview': x.overview,
            'path': x.path,
            'poster': x.poster,
            'profileId': x.profileId,
            'radarrId': x.radarrId,
            'sceneName': x.sceneName,
            'subtitles': x.subtitles,
            'tags': x.tags,
            'title': x.title,
            'year': x.year,
        }) for x in database.execute(stmt).all()]

        count = database.execute(
            select(func.count())
            .select_from(TableMovies)) \
            .scalar()

        # Include Plex movies if Plex integration is enabled
        if settings.general.use_plex:
            plex_stmt = select(
                TablePlexMovies.title.label('title'),
                TablePlexMovies.year.label('year'),
                TablePlexMovies.path.label('path'),
                TablePlexMovies.imdbId.label('imdbId'),
                TablePlexMovies.overview.label('overview'),
                TablePlexMovies.poster.label('poster'),
                TablePlexMovies.fanart.label('fanart'),
                TablePlexMovies.audio_language.label('audio_language'),
                TablePlexMovies.subtitles.label('subtitles'),
                TablePlexMovies.missing_subtitles.label('missing_subtitles'),
                TablePlexMovies.profileId.label('profileId'),
                TablePlexMovies.plexId.label('radarrId'),  # Use plexId as radarrId for compatibility
                TablePlexMovies.monitored.label('monitored')
            ).order_by(TablePlexMovies.title)
            
            # Apply filters if specific movie IDs requested
            if len(radarrId) != 0:
                plex_stmt = plex_stmt.where(TablePlexMovies.plexId.in_(radarrId))
            
            # Apply pagination for general requests
            if length > 0 and len(radarrId) == 0:
                plex_stmt = plex_stmt.limit(length).offset(start)
                
            # Execute Plex query and process results
            plex_results = [postprocess({
                'alternativeTitles': '[]',  # Plex doesn't have this field
                'audio_language': x.audio_language,
                'fanart': x.fanart,
                'imdbId': x.imdbId,
                'missing_subtitles': x.missing_subtitles if x.missing_subtitles else '[]',
                'monitored': x.monitored == 1,  # Convert to boolean
                'overview': x.overview,
                'path': x.path,
                'poster': x.poster,
                'profileId': x.profileId,
                'radarrId': x.radarrId,  # This is actually plexId
                'sceneName': '',  # Plex doesn't have sceneName
                'subtitles': x.subtitles if x.subtitles else '[]',
                'tags': '[]',  # Plex doesn't have tags - pass as string for ast.literal_eval
                'title': f"[Plex] {x.title}",  # Add [Plex] prefix to distinguish
                'year': str(x.year) if x.year else '',  # Convert to string for consistency
            }) for x in database.execute(plex_stmt).all()]
            
            # Combine results
            results.extend(plex_results)
            
            # Update count to include Plex movies
            plex_count = database.execute(
                select(func.count())
                .select_from(TablePlexMovies)) \
                .scalar()
            count += plex_count

        return marshal({'data': results, 'total': count}, self.get_response_model)

    post_request_parser = reqparse.RequestParser()
    post_request_parser.add_argument('radarrid', type=int, action='append', required=False, default=[],
                                     help='Radarr movie(s) ID')
    post_request_parser.add_argument('profileid', type=str, action='append', required=False, default=[],
                                     help='Languages profile(s) ID or "none"')

    @authenticate
    @api_ns_movies.doc(parser=post_request_parser)
    @api_ns_movies.response(204, 'Success')
    @api_ns_movies.response(401, 'Not Authenticated')
    @api_ns_movies.response(404, 'Languages profile not found')
    def post(self):
        """Update specific movies languages profile"""
        args = self.post_request_parser.parse_args()
        radarrIdList = args.get('radarrid')
        profileIdList = args.get('profileid')

        for idx in range(len(radarrIdList)):
            radarrId = radarrIdList[idx]
            profileId = profileIdList[idx]

            if profileId in None_Keys:
                profileId = None
            else:
                try:
                    profileId = int(profileId)
                except Exception:
                    return 'Languages profile not found', 404

            database.execute(
                update(TableMovies)
                .values(profileId=profileId)
                .where(TableMovies.radarrId == radarrId))

            list_missing_subtitles_movies(no=radarrId, send_event=False)

            event_stream(type='movie', payload=radarrId)
            event_stream(type='movie-wanted', payload=radarrId)
        event_stream(type='badges')

        return '', 204

    patch_request_parser = reqparse.RequestParser()
    patch_request_parser.add_argument('radarrid', type=int, required=False, help='Radarr movie ID')
    patch_request_parser.add_argument('action', type=str, required=False, help='Action to perform from ["scan-disk", '
                                                                               '"search-missing", "search-wanted", "sync"]')

    @authenticate
    @api_ns_movies.doc(parser=patch_request_parser)
    @api_ns_movies.response(204, 'Success')
    @api_ns_movies.response(400, 'Unknown action')
    @api_ns_movies.response(401, 'Not Authenticated')
    @api_ns_movies.response(500, 'Movie file not found. Path mapping issue?')
    def patch(self):
        """Run actions on specific movies"""
        args = self.patch_request_parser.parse_args()
        radarrid = args.get('radarrid')
        action = args.get('action')
        if action == "scan-disk":
            movies_scan_subtitles(radarrid)
            return '', 204
        elif action == "search-missing":
            try:
                movies_download_subtitles(radarrid)
            except OSError:
                return 'Movie file not found. Path mapping issue?', 500
            else:
                return '', 204
        elif action == "search-wanted":
            wanted_search_missing_subtitles_movies()
            return '', 204
        elif action == "sync":
            update_one_movie(radarrid, 'updated', True)
            return '', 204

        return 'Unknown action', 400
