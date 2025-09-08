# coding=utf-8

import json
import requests
import os
import logging

from flask_restx import Resource, Namespace, reqparse
from bs4 import BeautifulSoup as bso

from app.database import (TableEpisodes, TableShows, TableMovies, database, select, update,
                        TablePlexLibraries, TablePlexMovies, TablePlexShows, TablePlexEpisodes)
from subtitles.mass_download import episode_download_subtitles, movies_download_subtitles
from app.logger import logger
from api.plex.security import sanitize_log_data
from plex.operations import get_plex_server
from plex.content_discovery import PlexContentDiscoveryService
from datetime import datetime, timezone

from ..utils import authenticate


api_ns_webhooks_plex = Namespace('Webhooks Plex', description='Webhooks endpoint that can be configured in Plex to '
                                                              'trigger a subtitles search when playback start.')


@api_ns_webhooks_plex.route('webhooks/plex')
class WebHooksPlex(Resource):
    post_request_parser = reqparse.RequestParser()
    post_request_parser.add_argument('payload', type=str, required=True, help='Webhook payload')

    @authenticate
    @api_ns_webhooks_plex.doc(parser=post_request_parser)
    @api_ns_webhooks_plex.response(200, 'Success')
    @api_ns_webhooks_plex.response(204, 'Unhandled event or no processable data')
    @api_ns_webhooks_plex.response(400, 'Bad request - missing required data')
    @api_ns_webhooks_plex.response(401, 'Not Authenticated')
    @api_ns_webhooks_plex.response(404, 'IMDB series/movie ID not found')
    @api_ns_webhooks_plex.response(500, 'Internal server error')
    def post(self):
        """Trigger subtitles search on play media event in Plex"""
        try:
            args = self.post_request_parser.parse_args()
            json_webhook = args.get('payload')
            
            if not json_webhook:
                logger.debug('PLEX WEBHOOK: No payload received')
                return "No payload found in request", 400
            
            parsed_json_webhook = json.loads(json_webhook)
            
            # Check if this is a valid Plex webhook (should have 'event' field)
            if 'event' not in parsed_json_webhook:
                logger.debug('PLEX WEBHOOK: Invalid payload - missing "event" field')
                return "Invalid webhook payload - missing event field", 400
            
            event = parsed_json_webhook['event']
            
            # Handle different Plex events
            if event == 'media.play':
                return self._handle_media_play(parsed_json_webhook)
            elif event in ['library.new', 'library.on.deck']:
                return self._handle_library_update(parsed_json_webhook)
            elif event == 'media.scrobble':
                return self._handle_media_scrobble(parsed_json_webhook)
            else:
                logger.debug('PLEX WEBHOOK: Ignoring unhandled event "%s"', event)
                return 'Unhandled event', 204
                
        except json.JSONDecodeError as e:
            logger.debug('PLEX WEBHOOK: Failed to parse JSON. Error: %s. Payload: %s', 
                        str(e), sanitize_log_data(json_webhook) if json_webhook else 'None')
            return "Invalid JSON payload", 400
        except Exception as e:
            logger.error('PLEX WEBHOOK: Unexpected error: %s', str(e))
            return "Unexpected error processing webhook", 500

    def _handle_media_play(self, webhook_data):
        """Handle media.play events for subtitle download triggers."""
        try:
            # Check if Metadata key exists in the payload
            if 'Metadata' not in webhook_data:
                logger.debug('PLEX WEBHOOK: No Metadata in media.play payload')
                return "No Metadata found in JSON request body", 400
                
            if 'Guid' not in webhook_data['Metadata']:
                logger.debug('PLEX WEBHOOK: No GUID in Metadata for media.play event. Probably a pre-roll video.')
                return "No GUID found in JSON request body", 204

            media_type = webhook_data['Metadata']['type']

            if media_type == 'episode':
                season = webhook_data['Metadata']['parentIndex']
                episode = webhook_data['Metadata']['index']
            else:
                season = episode = None

            ids = []
            for item in webhook_data['Metadata']['Guid']:
                splitted_id = item['id'].split('://')
                if len(splitted_id) == 2:
                    ids.append({splitted_id[0]: splitted_id[1]})
            if not ids:
                return 'No GUID found', 204

            # Update Plex tables and trigger subtitle download
            self._update_plex_tables_from_webhook(webhook_data)

            # Original subtitle download logic (unchanged)
            if media_type == 'episode':
                try:
                    episode_imdb_id = [x['imdb'] for x in ids if 'imdb' in x][0]
                    r = requests.get(f'https://imdb.com/title/{episode_imdb_id}',
                                     headers={"User-Agent": os.environ["SZ_USER_AGENT"]})
                    soup = bso(r.content, "html.parser")
                    script_tag = soup.find(id='__NEXT_DATA__')
                    script_tag_json = script_tag.string
                    show_metadata_dict = json.loads(script_tag_json)
                    series_imdb_id = show_metadata_dict['props']['pageProps']['aboveTheFoldData']['series']['series']['id']
                except Exception:
                    logger.debug('BAZARR is unable to get series IMDB id.')
                    return 'IMDB series ID not found', 404
                else:
                    sonarrEpisodeId = database.execute(
                        select(TableEpisodes.sonarrEpisodeId)
                        .select_from(TableEpisodes)
                        .join(TableShows)
                        .where(TableShows.imdbId == series_imdb_id,
                               TableEpisodes.season == season,
                               TableEpisodes.episode == episode)) \
                        .first()

                    if sonarrEpisodeId:
                        episode_download_subtitles(no=sonarrEpisodeId.sonarrEpisodeId, send_progress=True)
            else:
                try:
                    movie_imdb_id = [x['imdb'] for x in ids if 'imdb' in x][0]
                except Exception:
                    logger.debug('BAZARR is unable to get movie IMDB id.')
                    return 'IMDB movie ID not found', 404
                else:
                    radarrId = database.execute(
                        select(TableMovies.radarrId)
                        .where(TableMovies.imdbId == movie_imdb_id)) \
                        .first()

                    if radarrId:
                        movies_download_subtitles(no=radarrId.radarrId)

            return '', 200
            
        except Exception as e:
            logger.error(f'PLEX WEBHOOK: Error handling media.play event: {e}')
            return "Error processing media.play event", 500

    def _handle_library_update(self, webhook_data):
        """Handle library.new and library.on.deck events for content updates."""
        try:
            # Check if Metadata key exists in the payload
            if 'Metadata' not in webhook_data:
                logger.debug('PLEX WEBHOOK: No Metadata in library update payload')
                return "No metadata in library update", 204

            logger.info(f'PLEX WEBHOOK: Processing {webhook_data["event"]} event')
            
            # Update Plex tables with new/updated content
            self._update_plex_tables_from_webhook(webhook_data)
            
            return '', 200
            
        except Exception as e:
            logger.error(f'PLEX WEBHOOK: Error handling library update event: {e}')
            return "Error processing library update", 500

    def _handle_media_scrobble(self, webhook_data):
        """Handle media.scrobble events for playback tracking."""
        try:
            logger.debug(f'PLEX WEBHOOK: Processing media.scrobble event')
            
            # Update playback information in Plex tables
            self._update_plex_tables_from_webhook(webhook_data)
            
            return '', 200
            
        except Exception as e:
            logger.error(f'PLEX WEBHOOK: Error handling media.scrobble event: {e}')
            return "Error processing media.scrobble", 500

    def _update_plex_tables_from_webhook(self, webhook_data):
        """Update Plex tables based on webhook metadata."""
        try:
            metadata = webhook_data.get('Metadata')
            if not metadata:
                return

            media_type = metadata.get('type')
            plex_id = str(metadata.get('ratingKey', ''))
            
            if not plex_id:
                logger.debug('PLEX WEBHOOK: No ratingKey found in metadata')
                return

            logger.debug(f'PLEX WEBHOOK: Updating {media_type} with Plex ID: {plex_id}')

            # Get Plex server connection and content discovery service
            try:
                plex_server = get_plex_server()
                content_discovery = PlexContentDiscoveryService()
            except Exception as e:
                logger.warning(f'PLEX WEBHOOK: Could not connect to Plex server: {e}')
                return

            # Update content based on media type
            if media_type == 'movie':
                self._update_movie_from_webhook(plex_server, content_discovery, plex_id, metadata)
            elif media_type == 'show':
                self._update_show_from_webhook(plex_server, content_discovery, plex_id, metadata)
            elif media_type == 'episode':
                self._update_episode_from_webhook(plex_server, content_discovery, plex_id, metadata)

        except Exception as e:
            logger.error(f'PLEX WEBHOOK: Error updating Plex tables: {e}')

    def _update_movie_from_webhook(self, plex_server, content_discovery, plex_id, metadata):
        """Update movie in Plex tables from webhook data."""
        try:
            # Check if movie exists in Plex tables
            existing = database.execute(
                select(TablePlexMovies)
                .where(TablePlexMovies.plex_id == plex_id)
            ).first()

            if existing:
                # Update existing movie timestamp
                database.execute(
                    update(TablePlexMovies)
                    .where(TablePlexMovies.plex_id == plex_id)
                    .values(updated_at_timestamp=datetime.now(timezone.utc))
                )
                logger.debug(f'PLEX WEBHOOK: Updated movie timestamp for Plex ID: {plex_id}')
            else:
                # New movie - fetch from Plex and add to database
                try:
                    movie = plex_server.fetchItem(int(plex_id))
                    library_key = str(movie.librarySectionID)
                    
                    # Use content discovery to add new movie
                    content_discovery._process_single_movie(movie, library_key, "Webhook")
                    logger.info(f'PLEX WEBHOOK: Added new movie from webhook: {movie.title}')
                    
                except Exception as e:
                    logger.error(f'PLEX WEBHOOK: Could not fetch movie {plex_id}: {e}')

        except Exception as e:
            logger.error(f'PLEX WEBHOOK: Error updating movie from webhook: {e}')

    def _update_show_from_webhook(self, plex_server, content_discovery, plex_id, metadata):
        """Update show in Plex tables from webhook data."""
        try:
            # Check if show exists in Plex tables
            existing = database.execute(
                select(TablePlexShows)
                .where(TablePlexShows.plex_id == plex_id)
            ).first()

            if existing:
                # Update existing show timestamp
                database.execute(
                    update(TablePlexShows)
                    .where(TablePlexShows.plex_id == plex_id)
                    .values(updated_at_timestamp=datetime.now(timezone.utc))
                )
                logger.debug(f'PLEX WEBHOOK: Updated show timestamp for Plex ID: {plex_id}')
            else:
                # New show - fetch from Plex and add to database
                try:
                    show = plex_server.fetchItem(int(plex_id))
                    library_key = str(show.librarySectionID)
                    
                    # Use content discovery to add new show
                    content_discovery._process_single_show(show, library_key, "Webhook")
                    logger.info(f'PLEX WEBHOOK: Added new show from webhook: {show.title}')
                    
                except Exception as e:
                    logger.error(f'PLEX WEBHOOK: Could not fetch show {plex_id}: {e}')

        except Exception as e:
            logger.error(f'PLEX WEBHOOK: Error updating show from webhook: {e}')

    def _update_episode_from_webhook(self, plex_server, content_discovery, plex_id, metadata):
        """Update episode in Plex tables from webhook data."""
        try:
            # Check if episode exists in Plex tables
            existing = database.execute(
                select(TablePlexEpisodes)
                .where(TablePlexEpisodes.plex_id == plex_id)
            ).first()

            if existing:
                # Update existing episode timestamp
                database.execute(
                    update(TablePlexEpisodes)
                    .where(TablePlexEpisodes.plex_id == plex_id)
                    .values(updated_at_timestamp=datetime.now(timezone.utc))
                )
                logger.debug(f'PLEX WEBHOOK: Updated episode timestamp for Plex ID: {plex_id}')
            else:
                # New episode - fetch from Plex and add to database
                try:
                    episode = plex_server.fetchItem(int(plex_id))
                    show_plex_id = str(episode.grandparentRatingKey)
                    
                    # Ensure the parent show exists first
                    show_exists = database.execute(
                        select(TablePlexShows)
                        .where(TablePlexShows.plex_id == show_plex_id)
                    ).first()
                    
                    if not show_exists:
                        # Add parent show first
                        show = plex_server.fetchItem(int(show_plex_id))
                        library_key = str(show.librarySectionID)
                        content_discovery._process_single_show(show, library_key, "Webhook")
                    
                    # Use content discovery to add new episode
                    content_discovery._process_single_episode(episode, show_plex_id)
                    logger.info(f'PLEX WEBHOOK: Added new episode from webhook: {episode.title}')
                    
                except Exception as e:
                    logger.error(f'PLEX WEBHOOK: Could not fetch episode {plex_id}: {e}')

        except Exception as e:
            logger.error(f'PLEX WEBHOOK: Error updating episode from webhook: {e}')
