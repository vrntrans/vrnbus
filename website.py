import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import tornado.web
from tornado.concurrent import run_on_executor

from cds import UserLoc
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
            (r"/coddbus", MapHandler),
            (r"/(.*)", static_handler, {"path": Path("./fe"), "default_filename": "index.html"}),
        ]
        tornado.web.Application.__init__(self, handlers)
        self.cds = cds
        self.logger = logger


class BusInfoHandler(BaseHandler):
    executor = ThreadPoolExecutor()

    def bus_info_response(self, query, lat, lon):
        self.logger.info(f'Bus info query: "{query}"')
        user_loc = None
        if lat and lon:
            user_loc = UserLoc(float(lat), float(lon))
        response = self.cds.bus_request(*parse_routes(query.split()), user_loc=user_loc)
        response = {'q': query, 'text': response}
        self.write(json.dumps(response))
        self.caching()

    @run_on_executor
    def get(self):
        q = self.get_argument('q')
        lat = self.get_argument('lat', None)
        lon = self.get_argument('lon', None)
        self.bus_info_response(q, lat, lon)


class ArrivalHandler(BaseHandler):
    executor = ThreadPoolExecutor()
    def arrival_response(self, lat, lon):
        matches = self.cds.matches_bus_stops(lat, lon)
        self.logger.info(f'{lat};{lon} {";".join([str(i) for i in matches])}')
        result = self.cds.next_bus_for_matches(matches, [])
        response = {'lat': lat, 'lon': lon, 'text': result[0], 'routes': result[1]}
        self.write(json.dumps(response))
        self.caching()

    @run_on_executor
    def get(self):
        (lat, lon) = (float(self.get_argument(x)) for x in ('lat', 'lon'))
        self.arrival_response(lat, lon)

class MapHandler(BaseHandler):
    executor = ThreadPoolExecutor()

    def bus_info_response(self, query):
        self.logger.info(f'Bus info query: "{query}"')

        response = self.cds.load_codd_buses(parse_routes(query.split())[1])
        response = {'q': query, 'result': [x._asdict() for x in response]}
        self.write(json.dumps(response))
        self.caching()

    @run_on_executor
    def get(self):
        q = self.get_argument('q')
        self.bus_info_response(q)
