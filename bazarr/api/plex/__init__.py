# coding=utf-8

from flask_restx import Namespace
api_ns_plex = Namespace('Plex Authentication', description='Plex OAuth and server management')

from .oauth import *  # noqa
from .library_sync import api_ns_plex_library  # noqa

api_ns_list_plex = [api_ns_plex, api_ns_plex_library]
