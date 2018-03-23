import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import tornado.web
from tornado.concurrent import run_on_executor

import helpers
from abuse_checker import AbuseChecker
from tracking import WebEvent, EventTracker

if 'DYNO' in os.environ:
    debug = False
else:
    debug = True

FULL_ACCESS_KEY = os.environ.get('FULL_ACCESS_KEY', '?key=42')


# noinspection PyAbstractClass
class NoCacheStaticFileHandler(tornado.web.StaticFileHandler):
    def set_extra_headers(self, path):
        self.set_header("Cache-control", "no-cache")


class BaseHandler(tornado.web.RequestHandler):
    executor = ThreadPoolExecutor()

    def track(self, event: WebEvent, *params):
        self.tracker.web(event, self.remote_ip, *params, self.user_agent)

    def data_received(self, chunk):
        pass

    def set_extra_headers(self, _):
        self.set_header("Tk", "N")
        self.caching()

    def caching(self, max_age=30):
        self.set_header("Cache-Control", f"max-age={max_age}")

    @property
    def remote_ip(self):
        return self.request.headers.get('X-Forwarded-For',
                                        self.request.headers.get('X-Real-Ip', self.request.remote_ip))

    @property
    def anti_abuser(self):
        return self.application.anti_abuser

    @property
    def full_access(self):
        return FULL_ACCESS_KEY in self.request.headers["Referer"]

    @property
    def user_agent(self):
        return self.request.headers["User-Agent"]

    @property
    def processor(self):
        return self.application.processor

    @property
    def logger(self):
        return self.application.logger

    @property
    def tracker(self) -> EventTracker:
        return self.application.tracker


class BusSite(tornado.web.Application):
    def __init__(self, processor, logger, tracker: EventTracker, anti_abuser: AbuseChecker):
        static_handler = tornado.web.StaticFileHandler if not debug else NoCacheStaticFileHandler
        handlers = [
            (r"/arrival", ArrivalHandler),
            (r"/busmap", BusInfoHandler),
            (r"/businfolist", BusInfoHandler),
            (r"/buslist", BusListHandler),
            (r"/bus_stop_search", BusStopSearchHandler),
            (r"/ping", PingHandler),
            (r"/(.*.json)", static_handler, {"path": Path("./")}),
            (r"/(.*)", static_handler, {"path": Path("./fe"), "default_filename": "index.html"}),
        ]
        tornado.web.Application.__init__(self, handlers)
        self.logger = logger
        self.processor = processor
        self.tracker = tracker
        self.anti_abuser = anti_abuser


class PingHandler(BaseHandler):
    @run_on_executor
    def get(self):
        self.logger.info('PING')
        self.write("PONG")
        self.caching(max_age=600)


class BusInfoHandler(BaseHandler):
    def bus_info_response(self, src, query, lat, lon):
        is_map = src == 'map'
        event = WebEvent.BUSMAP if is_map else WebEvent.BUSINFO
        if not self.anti_abuser.add_user_event(event, self.remote_ip) and not self.full_access:
            self.track(WebEvent.ABUSE, query, lat, lon)
            return self.send_error(500)
        self.track(event, src, query, lat, lon)
        response = self.processor.get_bus_info(query, lat, lon)
        self.write(json.dumps(response, cls=helpers.CustomJsonEncoder))
        self.caching()

    @run_on_executor
    def get(self):
        q = self.get_argument('q')
        src = self.get_argument('src', None)
        lat = self.get_argument('lat', None)
        lon = self.get_argument('lon', None)
        self.bus_info_response(src, q, lat, lon)


class ArrivalHandler(BaseHandler):
    def arrival_response(self):
        (lat, lon) = (float(self.get_argument(x)) for x in ('lat', 'lon'))
        query = self.get_argument('q')
        self.track(WebEvent.ARRIVAL, query, lat, lon)
        response = self.processor.get_arrival(query, lat, lon)
        self.write(json.dumps(response))
        self.caching()

    @run_on_executor
    def get(self):
        self.arrival_response()


class BusListHandler(BaseHandler):
    def _response(self):
        self.logger.info(f'Bus list query')

        response = self.processor.get_bus_list()
        self.write(json.dumps(response))
        self.caching(max_age=24 * 60 * 60)

    @run_on_executor
    def get(self):
        self._response()


class BusStopSearchHandler(BaseHandler):
    def _response(self):
        query = self.get_argument('q')
        station_query = self.get_argument('station')
        self.track(WebEvent.BUSSTOP, query, station_query)
        response = self.processor.get_arrival_by_name(query, station_query)
        self.write(json.dumps(response))
        self.caching()

    @run_on_executor
    def get(self):
        self._response()
