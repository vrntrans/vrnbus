import json
from pathlib import Path

import tornado.web

from helpers import parse_routes


# noinspection PyAbstractClass
class NoCacheStaticFileHandler(tornado.web.StaticFileHandler):
    def set_extra_headers(self, path):
        self.set_header("Cache-control", "no-cache")


class BaseHandler(tornado.web.RequestHandler):
    def data_received(self, data):
        pass

    def caching(self, max_age=30):
        self.set_header("Cache-Control", f"max-age={max_age}")

    @property
    def cds(self):
        return self.application.cds

    @property
    def logger(self):
        return self.application.logger


class BusSite(tornado.web.Application):
    def __init__(self, cds, logger, debug):
        static_handler = tornado.web.StaticFileHandler if not debug else NoCacheStaticFileHandler
        handlers = [
            (r"/arrival", ArrivalHandler),
            (r"/businfo", BusInfoHandler),
            (r"/(.*)", static_handler, {"path": Path("./fe"), "default_filename": "index.html"}),
        ]
        tornado.web.Application.__init__(self, handlers)
        self.cds = cds
        self.logger = logger


class BusInfoHandler(BaseHandler):
    def bus_info_response(self, query):
        self.logger.info(f'Bus info query: "{query}"')
        response = self.cds.bus_request(*parse_routes(query.split()))
        response = {'q': query, 'text': response}
        self.write(json.dumps(response))
        self.caching()

    def get(self):
        self.bus_info_response(self.get_argument('q'))


class ArrivalHandler(BaseHandler):
    def arrival_response(self, lat, lon):
        matches = self.cds.matches_bus_stops(lat, lon)
        self.logger.info(f'{lat};{lon} {";".join([str(i) for i in matches])}')
        result = self.cds.next_bus_for_matches(matches, [])
        response = {'lat': lat, 'lon': lon, 'text': result}
        self.write(json.dumps(response))
        self.caching()

    def get(self):
        (lat, lon) = (float(self.get_argument(x)) for x in ('lat', 'lon'))
        self.arrival_response(lat, lon)
