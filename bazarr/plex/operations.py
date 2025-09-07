# coding=utf-8
from datetime import datetime
from app.config import settings
from plexapi.server import PlexServer
from plexapi.myplex import MyPlexAccount
import logging
import base64
import json

logger = logging.getLogger(__name__)

# Constants
DATETIME_FORMAT = '%Y-%m-%d %H:%M:%S'


def _extract_plex_token(token_string: str) -> str:
    """
    Extract the actual Plex token from Bazarr's encrypted token format.
    Bazarr stores Plex tokens in a JWT-like format with base64 encoding.
    """
    try:
        # Check if this looks like a JWT-style token
        if '.' in token_string and len(token_string.split('.')) >= 2:
            # Split the token and decode the payload
            parts = token_string.split('.')
            payload = parts[0]
            
            # Add padding if needed for base64 decoding
            payload += '=' * (4 - len(payload) % 4)
            
            # Decode base64 and parse JSON
            decoded_bytes = base64.b64decode(payload)
            decoded_data = json.loads(decoded_bytes.decode('utf-8'))
            
            # Extract the actual token
            if 'token' in decoded_data:
                actual_token = decoded_data['token']
                logger.debug("Successfully extracted Plex token from encrypted format")
                return actual_token
            else:
                logger.warning("Token field not found in decoded data, using original token")
                return token_string
        else:
            # If it doesn't look like JWT format, use as-is
            logger.debug("Token doesn't appear to be encrypted, using as-is")
            return token_string
            
    except Exception as e:
        logger.warning(f"Failed to extract token from encrypted format: {e}, using original")
        return token_string


def get_plex_server() -> PlexServer:
    """Connect to the Plex server and return the server instance."""
    try:
        # Try direct connection first
        return _connect_direct_to_plex()
    
    except Exception as direct_error:
        logger.warning(f"Direct connection failed: {direct_error}")
        
        # If direct connection fails, try MyPlex authentication
        try:
            logger.info("Attempting MyPlex authentication as fallback...")
            return _connect_via_myplex()
        
        except Exception as myplex_error:
            logger.error(f"MyPlex authentication also failed: {myplex_error}")
            logger.error(f"Current Plex config - IP: '{settings.plex.ip}', Port: {settings.plex.port}, SSL: {settings.plex.ssl}")
            if hasattr(settings.plex, 'server_url'):
                logger.error(f"Server URL: '{settings.plex.server_url}'")
            
            # Re-raise the original direct connection error
            raise direct_error


def _connect_direct_to_plex() -> PlexServer:
    """Attempt direct connection to Plex server using configured URL/token."""
    # Check if we have a configured server_url (preferred method)
    if hasattr(settings.plex, 'server_url') and settings.plex.server_url:
        baseurl = settings.plex.server_url
        logger.debug(f"Using configured Plex server URL: {baseurl}")
    else:
        # Fallback to IP/port construction if server_url not available
        if not settings.plex.ip:
            raise ValueError("Plex server IP address is not configured. Please configure Plex integration in Bazarr settings.")
        
        protocol = "https://" if settings.plex.ssl else "http://"
        baseurl = f"{protocol}{settings.plex.ip}:{settings.plex.port}"
        logger.debug(f"Using constructed Plex server URL: {baseurl}")
    
    # Use token if available, fallback to apikey
    auth_token = None
    if hasattr(settings.plex, 'token') and settings.plex.token:
        auth_token = _extract_plex_token(settings.plex.token)
        logger.debug("Using extracted Plex token for authentication")
    elif settings.plex.apikey:
        auth_token = settings.plex.apikey
        logger.debug("Using Plex API key for authentication")
    else:
        raise ValueError("Plex authentication token/API key is not configured. Please configure Plex integration in Bazarr settings.")
    
    # Create and test connection
    plex_server = PlexServer(baseurl, auth_token)
    
    # Test connection by getting server info
    _ = plex_server.version
    logger.info(f"Direct connection successful: {plex_server.friendlyName} (version {plex_server.version})")
    
    return plex_server


def _connect_via_myplex() -> PlexServer:
    """Attempt connection via MyPlex account with server discovery."""
    # Check if we have server identification info
    if not (hasattr(settings.plex, 'server_name') and settings.plex.server_name):
        raise ValueError("Server name not configured for MyPlex authentication")
    
    # Get authentication token for MyPlex
    auth_token = None
    if hasattr(settings.plex, 'token') and settings.plex.token:
        auth_token = _extract_plex_token(settings.plex.token)
    elif settings.plex.apikey:
        auth_token = settings.plex.apikey
    else:
        raise ValueError("No authentication token available for MyPlex")
    
    # Connect to MyPlex account 
    account = MyPlexAccount(token=auth_token)
    
    # Find the server by name or machine ID
    server_resource = None
    
    # Try by server name first
    try:
        server_resource = account.resource(settings.plex.server_name)
        logger.info(f"Found server by name: {settings.plex.server_name}")
    except:
        # Try by machine ID if available
        if hasattr(settings.plex, 'server_machine_id') and settings.plex.server_machine_id:
            for resource in account.resources():
                if resource.clientIdentifier == settings.plex.server_machine_id:
                    server_resource = resource
                    logger.info(f"Found server by machine ID: {settings.plex.server_machine_id}")
                    break
    
    if not server_resource:
        available_servers = [r.name for r in account.resources() if hasattr(r, 'name')]
        raise ValueError(f"Plex server '{settings.plex.server_name}' not found. Available servers: {available_servers}")
    
    # Connect to the server
    plex_server = server_resource.connect()
    logger.info(f"MyPlex connection successful: {plex_server.friendlyName} (version {plex_server.version})")
    
    return plex_server


def update_added_date(video, added_date: str) -> None:
    """Update the added date of a video in Plex."""
    try:
        updates = {"addedAt.value": added_date}
        video.edit(**updates)
        logger.info(f"Updated added date for {video.title} to {added_date}")
    except Exception as e:
        logger.error(f"Failed to update added date for {video.title}: {e}")
        raise


def plex_set_movie_added_date_now(movie_metadata) -> None:
    """
    Update the added date of a movie in Plex to the current datetime.

    :param movie_metadata: Metadata object containing the movie's IMDb ID.
    """
    try:
        plex = get_plex_server()
        library = plex.library.section(settings.plex.movie_library)
        video = library.getGuid(guid=movie_metadata.imdbId)
        current_date = datetime.now().strftime(DATETIME_FORMAT)
        update_added_date(video, current_date)
    except Exception as e:
        logger.error(f"Error in plex_set_movie_added_date_now: {e}")


def plex_set_episode_added_date_now(episode_metadata) -> None:
    """
    Update the added date of a TV episode in Plex to the current datetime.

    :param episode_metadata: Metadata object containing the episode's IMDb ID, season, and episode number.
    """
    try:
        plex = get_plex_server()
        library = plex.library.section(settings.plex.series_library)
        show = library.getGuid(episode_metadata.imdbId)
        episode = show.episode(season=episode_metadata.season, episode=episode_metadata.episode)
        current_date = datetime.now().strftime(DATETIME_FORMAT)
        update_added_date(episode, current_date)
    except Exception as e:
        logger.error(f"Error in plex_set_episode_added_date_now: {e}")


def plex_update_library(is_movie_library: bool) -> None:
    """
    Trigger a library update for the specified library type.

    :param is_movie_library: True for movie library, False for series library.
    """
    try:
        plex = get_plex_server()
        library_name = settings.plex.movie_library if is_movie_library else settings.plex.series_library
        library = plex.library.section(library_name)
        library.update()
        logger.info(f"Triggered update for library: {library_name}")
    except Exception as e:
        logger.error(f"Error in plex_update_library: {e}")