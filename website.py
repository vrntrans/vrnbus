import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import tornado.web
from tornado.concurrent import run_on_executor

import helpers
from data_types import UserLoc
from helpers import parse_routes, natural_sort_key

if 'DYNO' in os.environ:
    debug = False
else:
    debug = True

# noinspection PyAbstractClass
class NoCacheStaticFileHandler(tornado.web.StaticFileHandler):
    def set_extra_headers(self, path):
        self.set_header("Cache-control", "no-cache")


class BaseHandler(tornado.web.RequestHandler):
    executor = ThreadPoolExecutor()

    def data_received(self, chunk):
        pass

    def set_extra_headers(self, _):
        self.set_header("Tk", "N")
        self.caching()

    def caching(self, max_age=30):
        self.set_header("Cache-Control", f"max-age={max_age}")

    @property
    def cds(self):
        return self.application.cds

    @property
    def logger(self):
        return self.application.logger


class BusSite(tornado.web.Application):
    def __init__(self, cds, logger):
        static_handler = tornado.web.StaticFileHandler if not debug else NoCacheStaticFileHandler
        handlers = [
            (r"/arrival", ArrivalHandler),
            (r"/businfo", BusInfoHandler),
            (r"/buslist", BusListHandler),
            (r"/bus_stop_search", BusStopSearchHandler),
            (r"/coddbus", MapHandler),
            (r"/ping", PingHandler),
            (r"/(.*)", static_handler, {"path": Path("./fe"), "default_filename": "index.html"}),
        ]
        tornado.web.Application.__init__(self, handlers)
        self.cds = cds
        self.logger = logger


class PingHandler(BaseHandler):
    @run_on_executor
    def get(self):
        self.logger.info('PING')
        self.write("PONG")
        self.caching(max_age=600)


class BusInfoHandler(BaseHandler):
    def bus_info_response(self, query, lat, lon):
        self.logger.info(f'Bus info query: "{query}"')
        user_loc = None
        if lat and lon:
            user_loc = UserLoc(float(lat), float(lon))
        result = self.cds.bus_request(parse_routes(query), user_loc=user_loc, short_format=True)
        response = {'q': query, 'text': result[0],
                    'buses': [(x[0]._asdict(), x[1]._asdict() if x[1] else {}) for x in result[1]]}
        self.write(json.dumps(response, cls=helpers.CustomJsonEncoder))
        self.caching()

    @run_on_executor
    def get(self):
        q = self.get_argument('q')
        lat = self.get_argument('lat', None)
        lon = self.get_argument('lon', None)
        self.bus_info_response(q, lat, lon)


class ArrivalHandler(BaseHandler):
    def arrival_response(self):
        (lat, lon) = (float(self.get_argument(x)) for x in ('lat', 'lon'))
        query = self.get_argument('q')

        new_version = self.get_argument('old', '') != 'true'

        matches = self.cds.matches_bus_stops(lat, lon)
        self.logger.info(f'{lat};{lon} {";".join([str(i) for i in matches])}')
        func = self.cds.next_bus_for_matches_alt if new_version else self.cds.next_bus_for_matches
        result = func(tuple(matches), parse_routes(query))
        response = {'lat': lat, 'lon': lon, 'text': result[0], 'header': result[1], 'bus_stops': result[2]}
        self.write(json.dumps(response))
        self.caching()

    @run_on_executor
    def get(self):
        self.arrival_response()


class MapHandler(BaseHandler):
    def bus_info_response(self, query):
        self.logger.info(f'Bus info query: "{query}"')

        response = self.cds.load_codd_buses(parse_routes(query)[1])
        response = {'q': query, 'result': [x._asdict() for x in response]}
        self.write(json.dumps(response))
        self.caching()

    @run_on_executor
    def get(self):
        q = self.get_argument('q')
        self.bus_info_response(q)


class BusListHandler(BaseHandler):
    def _response(self):
        self.logger.info(f'Bus list query')

        response = list(self.cds.codd_routes.keys())
        response.sort(key=natural_sort_key)
        response = {'result': response}
        self.write(json.dumps(response))
        self.caching(max_age=24 * 60 * 60)

    @run_on_executor
    def get(self):
        self._response()


class BusStopSearchHandler(BaseHandler):
    def _response(self):
        query = self.get_argument('q')
        station_query = self.get_argument('station')
        new_version = self.get_argument('old', '') != 'true'

        result_tuple = self.cds.next_bus(station_query, parse_routes(query), new_version)

        response = {'text': result_tuple[0], 'header': result_tuple[1], 'bus_stops': result_tuple[2]}
        self.write(json.dumps(response))
        self.caching()

    @run_on_executor
    def get(self):
        self._response()

