import datetime
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import tornado.web
from tornado.concurrent import run_on_executor

from cds import UserLoc
from helpers import parse_routes, natural_sort_key


# noinspection PyAbstractClass
class NoCacheStaticFileHandler(tornado.web.StaticFileHandler):
    def set_extra_headers(self, path):
        self.set_header("Cache-control", "no-cache")


class BaseHandler(tornado.web.RequestHandler):
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
    def __init__(self, cds, logger, debug):
        static_handler = tornado.web.StaticFileHandler if not debug else NoCacheStaticFileHandler
        handlers = [
            (r"/arrival", ArrivalHandler),
            (r"/businfo", BusInfoHandler),
            (r"/buslist", BusListHandler),
            (r"/coddbus", MapHandler),
            (r"/ping", PingHandler),
            (r"/(.*)", static_handler, {"path": Path("./fe"), "default_filename": "index.html"}),
        ]
        tornado.web.Application.__init__(self, handlers)
        self.cds = cds
        self.logger = logger


class PingHandler(BaseHandler):
    executor = ThreadPoolExecutor()

    @run_on_executor
    def get(self):
        self.logger.info('PING')
        self.write("PONG")
        self.caching(max_age=600)


class BusInfoHandler(BaseHandler):
    executor = ThreadPoolExecutor()

    def bus_info_response(self, query, lat, lon):
        self.logger.info(f'Bus info query: "{query}"')
        user_loc = None
        if lat and lon:
            user_loc = UserLoc(float(lat), float(lon))
        result = self.cds.bus_request(*parse_routes(query), user_loc=user_loc, short_format=True)
        response = {'q': query, 'text': result[0],
                    'buses': [(x[0]._asdict(), x[1]._asdict() if x[1] else {}) for x in result[1]]}
        self.write(json.dumps(response, cls=DateTimeEncoder))
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

        response = self.cds.load_codd_buses(parse_routes(query)[1])
        response = {'q': query, 'result': [x._asdict() for x in response]}
        self.write(json.dumps(response))
        self.caching()

    @run_on_executor
    def get(self):
        q = self.get_argument('q')
        self.bus_info_response(q)


class BusListHandler(BaseHandler):
    executor = ThreadPoolExecutor()

    def _response(self):
        self.logger.info(f'Bus list query')

        response = list(self.cds.codd_routes.keys())
        response.sort(key=natural_sort_key)
        response = {'result': response}
        self.write(json.dumps(response))
        self.caching()

    @run_on_executor
    def get(self):
        self._response()


class DateTimeEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, datetime.datetime):
            return o.isoformat()

        return json.JSONEncoder.default(self, o)
