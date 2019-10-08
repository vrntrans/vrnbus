import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import List

import tornado.web

import helpers
from abuse_checker import AbuseChecker
from data_processors import WebDataProcessor
from db import session_scope
from models import RouteEdges
from tracking import WebEvent, EventTracker

if 'DYNO' in os.environ:
    debug = False
else:
    debug = True

FULL_ACCESS_KEY = os.environ.get('FULL_ACCESS_KEY', '')

try:
    import settings

    FULL_ACCESS_KEY = settings.FULL_ACCESS_KEY
except ImportError:
    FULL_ACCESS_KEY = os.environ.get('FULL_ACCESS_KEY', '')


# noinspection PyAbstractClass
class NoCacheStaticFileHandler(tornado.web.StaticFileHandler):
    def set_extra_headers(self, path):
        self.set_header("Cache-control", "no-cache")


class BaseHandler(tornado.web.RequestHandler):
    executor = ThreadPoolExecutor()

    def prepare(self):
        if not self.get_cookie("user_ip"):
            self.set_cookie("user_ip", self.remote_ip, expires_days=30)

    def track(self, event: WebEvent, *params):
        if 'CFNetwork' in self.user_agent:
            self.tracker.web(WebEvent.IOS, self.user_ip, *params, self.user_agent)
        elif 'Dalvik' in self.user_agent or 'Android' in self.user_agent:
            self.tracker.web(WebEvent.ANDROID, self.user_ip, *params, self.user_agent)
        else:
            self.tracker.web(WebEvent.WEB_SITE, self.user_ip, *params, self.user_agent)

        self.tracker.web(event, self.user_ip, *params, self.user_agent)

    def data_received(self, chunk):
        pass

    def set_extra_headers(self, _):
        self.set_header("Tk", "N")
        self.caching()

    def caching(self, max_age=15):
        self.set_header("Content-Type", "application/json; charset=utf-8")
        self.set_header("Cache-Control", f"max-age={max_age}")

    @property
    def user_ip(self):
        return self.get_cookie("user_ip", self.remote_ip)

    @property
    def remote_ip(self):
        return self.request.headers.get('X-Forwarded-For',
                                        self.request.headers.get('X-Real-Ip', self.request.remote_ip))

    @property
    def anti_abuser(self):
        return self.application.anti_abuser

    @property
    def referer(self):
        return self.request.headers.get("Referer", "")

    @property
    def full_access(self):
        return self.referer and FULL_ACCESS_KEY in self.referer

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

    @property
    def is_mobile(self):
        return any((x in self.user_agent for x in ['CFNetwork', 'Dalvik', 'Android',]))

class BusSite(tornado.web.Application):
    def __init__(self, processor: WebDataProcessor, logger, tracker: EventTracker, anti_abuser: AbuseChecker):
        static_handler = tornado.web.StaticFileHandler if not debug else NoCacheStaticFileHandler
        handlers = [
            (r"/arrival", ArrivalHandler),
            (r"/arrival_by_id", ArrivalByIdHandler),
            (r"/busmap", BusInfoHandler),
            (r"/businfolist", BusInfoHandler),
            (r"/buslist", BusListHandler),
            (r"/bus_stop_search", BusStopSearchHandler),
            (r"/bus_stops_routes", BusStopsRoutesHandler),
            (r"/bus_stations.json", BusStopsRoutesForAppsHandler),
            (r"/bus_stops", BusStopsHandler),
            (r"/fotobus_info", FotoBusHandler),
            (r"/bus_route_edges", BusRouteEdgesHandler),
            (r"/ping", PingHandler),
            (r"/(.*.json)", static_handler, {"path": Path("./")}),
            (r"/stats.html", StatsHandler),
            (r"/(.*)", static_handler, {"path": Path("./fe"), "default_filename": "index.html"}),
        ]
        tornado.web.Application.__init__(self, handlers, compress_response=True)
        self.logger = logger
        self.processor = processor
        self.tracker = tracker
        self.anti_abuser = anti_abuser


class PingHandler(BaseHandler):
    def get(self):
        self.logger.info('PING')
        self.write("PONG")
        self.caching(max_age=600)


class BusInfoHandler(BaseHandler):
    def bus_info_response(self, src, query, lat, lon, parent_url, hide_text):
        is_map = src == 'map'
        if self.referer and 'vrnbus.herokuapp.com' not in self.referer:
            self.track(WebEvent.FRAUD, self.referer, query, lat, lon)
        if parent_url:
            self.track(WebEvent.FRAUD, parent_url, query, lat, lon)
        event = WebEvent.BUSMAP if is_map else WebEvent.BUSINFO
        if self.user_ip != self.remote_ip:
            self.track(WebEvent.IPCHANGE, f'{self.user_ip} != {self.remote_ip}')
        if self.full_access:
            self.track(WebEvent.FULLINFO, self.referer, query, lat, lon)
        if not self.anti_abuser.add_user_event(event, self.user_ip) and not self.full_access:
            self.track(WebEvent.ABUSE, query, lat, lon)
            return self.send_error(500)
        self.track(event, src, query, lat, lon)
        response = self.processor.get_bus_info(query, lat, lon, self.full_access, hide_text)
        self.write(json.dumps(response, cls=helpers.CustomJsonEncoder))
        self.caching()

    def get(self):
        q = self.get_argument('q')
        src = self.get_argument('src', None)
        lat = self.get_argument('lat', None)
        lon = self.get_argument('lon', None)
        parent_url = self.get_argument('parentUrl', None)
        hide_text = self.get_argument('hide_text', None) is not None

        self.bus_info_response(src, q, lat, lon, parent_url, hide_text)


class ArrivalHandler(BaseHandler):
    def arrival_response(self):
        (lat, lon) = (float(self.get_argument(x)) for x in ('lat', 'lon'))
        query = self.get_argument('q')
        self.track(WebEvent.ARRIVAL, query, lat, lon)
        response = self.processor.get_arrival(query, lat, lon)
        self.write(json.dumps(response, cls=helpers.CustomJsonEncoder))
        self.caching()

    def get(self):
        self.arrival_response()


class ArrivalByIdHandler(BaseHandler):
    def arrival_response(self):
        busstop_id = int(self.get_argument('id'))
        query = self.get_argument('q', "")
        self.track(WebEvent.ARRIVAL, query, busstop_id)
        response = self.processor.get_arrival_by_id(query, busstop_id)
        self.write(json.dumps(response, cls=helpers.CustomJsonEncoder))
        self.caching()

    def get(self):
        self.arrival_response()


class BusListHandler(BaseHandler):
    def _response(self):
        self.logger.info(f'Bus list query')

        response = self.processor.get_bus_list()
        self.write(json.dumps(response))
        if response:
            self.caching(max_age=24 * 60 * 60)

    def get(self):
        self._response()


class BusStopsHandler(BaseHandler):
    def _response(self):
        self.logger.info(f'Bus list query')

        response = self.processor.get_bus_stops()
        self.write(json.dumps(response, ensure_ascii=False))
        if response:
            self.caching(max_age=24 * 60 * 60)

    def get(self):
        self._response()

class BusStopsRoutesForAppsHandler(BaseHandler):
    def _response(self):
        self.logger.info(f'Bus list query')

        response = self.processor.get_bus_stops_for_routes_for_apps()
        self.write(json.dumps(response, ensure_ascii=False, indent=1, cls=helpers.CustomJsonEncoder))
        if response:
            self.caching(max_age=24 * 60 * 60)

    def get(self):
        self._response()

class BusStopsRoutesHandler(BaseHandler):
    def _response(self):
        self.logger.info(f'Bus list query')

        response = self.processor.get_bus_stops_for_routes()
        self.write(json.dumps(response, ensure_ascii=False))
        if response:
            self.caching(max_age=24 * 60 * 60)

    def get(self):
        self._response()


class BusStopSearchHandler(BaseHandler):
    def _response(self):
        query = self.get_argument('q')
        station_query = self.get_argument('station')
        self.track(WebEvent.BUSSTOP, query, station_query)
        response = self.processor.get_arrival_by_name(query, station_query)
        self.write(json.dumps(response, cls=helpers.CustomJsonEncoder))
        self.caching()

    def get(self):
        self._response()


class FotoBusHandler(BaseHandler):
    def _response(self):
        name = self.get_argument('name')
        self.track(WebEvent.FOTOBUS, name)
        links = self.processor.get_fotobus_url(name)
        if links:
            self.redirect(links[0])
        else:
            self.send_error(404)

    def get(self):
        self._response()


class StatsHandler(BaseHandler):
    def arrival_response(self):
        self.track(WebEvent.USER_STATS)
        response = self.processor.get_stats()
        self.write(response)
        self.caching()

    def get(self):
        self.arrival_response()

class BusRouteEdgesHandler(BaseHandler):
    def arrival_response(self):
        data = tornado.escape.json_decode(self.request.body)
        self.write(data)
        self.caching()

    def post(self):
        data = tornado.escape.json_decode(self.request.body)
        edge_key = json.dumps(data.get("edge_key"))
        points = json.dumps(data.get("points"))
        with session_scope(f'RouteEdges id {edge_key}') as session:
            edge = session.query(RouteEdges).filter_by(edge_key=edge_key).first()
            if not edge:
                edge = RouteEdges(edge_key=edge_key)
                session.add(edge)
            edge.points = points
            session.commit()

    def get(self):
        with session_scope(f'Return all RouteEdges') as session:
            edges: List[RouteEdges] = session.query(RouteEdges).all()
            result = [{"edge_key":  json.loads(x.edge_key),
                    "points": json.loads(x.points)} for x in edges]
            self.write(json.dumps(result))
