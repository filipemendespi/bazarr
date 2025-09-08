# coding=utf-8

"""
Plex API namespace registration

This module centralizes all Plex-related API endpoints and registers them
with the Flask-RESTX API system.
"""

from .plex_sync import api_ns_plex_sync
from .plex_subtitles import api_ns_plex_subtitles

# List of all Plex API namespaces to be registered
api_ns_list_plex = [
    api_ns_plex_sync,
    api_ns_plex_subtitles,
]