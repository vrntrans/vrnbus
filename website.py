import json
import os
import socket
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlparse

import tornado.web
import tornado.iostream
import tornado.httpclient
import tornado.httputil
from tornado.concurrent import run_on_executor

import helpers
from tracking import WebEvent, EventTracker

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

    def track(self, event: WebEvent, *params):
        remote_ip = self.request.headers.get('X-Forwarded-For',
                                             self.request.headers.get('X-Real-Ip', self.request.remote_ip))
        self.tracker.web(event, remote_ip, *params)

    def data_received(self, chunk):
        pass

    def set_extra_headers(self, _):
        self.set_header("Tk", "N")
        self.caching()

    def caching(self, max_age=30):
        self.set_header("Cache-Control", f"max-age={max_age}")

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
    def __init__(self, processor, logger, tracker: EventTracker):
        static_handler = tornado.web.StaticFileHandler if not debug else NoCacheStaticFileHandler
        handlers = [
            (r"/arrival", ArrivalHandler),
            (r"/businfo", BusInfoHandler),
            (r"/buslist", BusListHandler),
            (r"/bus_stop_search", BusStopSearchHandler),
            (r"/ping", PingHandler),
            (r"/CitizenCoddWebMaps/(GetBusesServlet|GetRouteBuses|GetInfoOfBus|GetNextBus)", StubHandler),
            (r"/(.*)", static_handler, {"path": Path("./fe"), "default_filename": "index.html"}),
        ]
        tornado.web.Application.__init__(self, handlers)
        self.logger = logger
        self.processor = processor
        self.tracker = tracker


def fetch_request(url, callback, **kwargs):
    req = tornado.httpclient.HTTPRequest(url, **kwargs)
    client = tornado.httpclient.HTTPClient()
    response = client.fetch(req, raise_error=False)
    callback(response)

class StubHandler(BaseHandler):
    def get_data_from_codd(self):
        def handle_response(response):
            self.logger.info(response)
            if (response.error and not
            isinstance(response.error, tornado.httpclient.HTTPError)):
                self.set_status(500)
                self.logger.error(response.error)
            else:
                self.set_status(response.code, response.reason)
                self._headers = tornado.httputil.HTTPHeaders()  # clear tornado default header

                for header, v in response.headers.get_all():
                    if header not in ('Content-Length', 'Transfer-Encoding', 'Content-Encoding', 'Connection'):
                        self.add_header(header, v)  # some header appear multiple times, eg 'Set-Cookie'

                if response.body:
                    self.set_header('Content-Length', len(response.body))
                    self.write(response.body)
        base_uri = 'http://195.98.83.236:8080/'
        body = self.request.body
        if not body:
            body = None
        try:
            if 'Proxy-Connection' in self.request.headers:
                del self.request.headers['Proxy-Connection']
            self.logger.info(f'{base_uri}{self.request.uri}')
            fetch_request(
                f'{base_uri}{self.request.uri}', handle_response,
                method=self.request.method, body=body,
                headers=self.request.headers, follow_redirects=False,
                allow_nonstandard_methods=True)
        except tornado.httpclient.HTTPError as e:
            self.logger.error(e)
            if hasattr(e, 'response') and e.response:
                handle_response(e.response)
            else:
                self.set_status(500)
                self.write('Internal server error:\n' + str(e))

    def f(self, *args, **kwargs):
        self.logger.info(f"{self.request.method} {args} {kwargs}")
        self.get_data_from_codd()
        self.caching(max_age=600)

    def post(self, *args, **kwargs):
        self.f(*args, **kwargs)

    def get(self, *args, **kwargs):
        self.f(*args, **kwargs)

class PingHandler(BaseHandler):
    @run_on_executor
    def get(self):
        self.logger.info('PING')
        self.write("PONG")
        self.caching(max_age=600)


class BusInfoHandler(BaseHandler):
    def bus_info_response(self, query, lat, lon):
        self.track(WebEvent.BUSINFO, query, lat, lon)
        response = self.processor.get_bus_info(query, lat, lon)
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
