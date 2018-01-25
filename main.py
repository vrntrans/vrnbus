# #!/usr/bin/env python3.6
import json
import logging
import os
from pathlib import Path

from cds_request import CdsRequest
from helpers import parse_routes
from tgbot import BusBot

# Enable logging
logging.basicConfig(format='%(asctime)s - %(levelname)s [%(filename)s:%(lineno)s %(funcName)20s] %(message)s',
                    level=logging.INFO)

logger = logging.getLogger(__name__)

logger.info(os.environ)
if 'DYNO' in os.environ:
    debug = False
else:
    debug = True


user_settings = {}


# import unittest
#
# class TestSomeCases(unittest.TestCase):
#
#     def test_split(self):
#         input = ['104', 'Тр.', '17', '18']
#         expected = ['104', 'Тр. 17', '18']
#         self.assertEqual(parse_routes(input), expected)
#
#     def test_split_pro(self):
#         input = ['104', 'Тр.', '17', '18']
#         expected = ['104', 'Тр. 17', '18']
#         self.assertEqual(parse_routes(input), expected)


import tornado.web

root = Path("./fe")
port = 8080

class NoCacheStaticFileHandler(tornado.web.StaticFileHandler):
    def set_extra_headers(self, path):
        self.set_header("Cache-control", "no-cache")

static_handler = tornado.web.StaticFileHandler if not debug else NoCacheStaticFileHandler

class BaseHandler(tornado.web.RequestHandler):
    @property
    def cds(self):
        return self.application.cds

class BusSite(tornado.web.Application):
    def __init__(self, cds):
        handlers = [
                (r"/arrival", ArrivalHandler),
                (r"/businfo", BusInfoHandler),
                (r"/(.*)", static_handler, {"path": Path("./fe"), "default_filename": "index.html"}),
            ]
        tornado.web.Application.__init__(self, handlers)
        self.cds = cds

class BusInfoHandler(BaseHandler):
    def _caching(self):
        self.set_header("Cache-Control", "max-age=30")

    def bus_info_response(self, query):
        (full_info, routes, filter) = parse_routes(query.split())
        logger.info(f'Bus info query: "{query}"')
        response = self.cds.bus_request(full_info, routes, filter)
        response = {'q': query, 'text': response}
        self.write(json.dumps(response))
        self._caching()

    def get(self):
        self.bus_info_response(self.get_argument('q'))


class ArrivalHandler(BaseHandler):
    def _caching(self):
        self.set_header("Cache-Control", "max-age=30")

    def arrival_response(self, lat, lon):
        matches = self.cds.matches_bus_stops(lat, lon)
        result = self.cds.next_bus_for_matches(matches, [])
        response = {'lat': lat, 'lon': lon, 'text': result}
        self.write(json.dumps(response))
        self._caching()

    def get(self):
        (lat, lon) = (float(self.get_argument(x)) for x in ('lat', 'lon') )
        self.arrival_response(lat, lon)


if __name__ == "__main__":
    cds = CdsRequest(logger)
    bot = BusBot(cds, user_settings, logger, debug)

    application = BusSite(cds)
    application.listen(os.environ.get('PORT', port))
    tornado.ioloop.IOLoop.instance().start()
