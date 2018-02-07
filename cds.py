import codecs
import json
import os
import time
from datetime import datetime, timedelta
from itertools import groupby
from logging import Logger
from pathlib import Path
from typing import NamedTuple, Iterable, Dict

import cachetools.func
import fdb
import pytz
import requests

from helpers import get_time, natural_sort_key, distance, distance_km, retry_multi

try:
    import settings

    CDS_HOST = settings.CDS_HOST
    CDS_DB_PATH = settings.CDS_DB_PATH
    CDS_USER = settings.CDS_USER
    CDS_PASS = settings.CDS_PASS
except ImportError:
    env = os.environ
    CDS_HOST = env['CDS_HOST']
    CDS_DB_PATH = env['CDS_DB_PATH']
    CDS_USER = env['CDS_USER']
    CDS_PASS = env['CDS_PASS']

if 'DYNO' in os.environ:
    debug = False
else:
    debug = True

cds_url_base = 'http://195.98.79.37:8080/CdsWebMaps/'
codd_base_usl = 'http://195.98.83.236:8080/CitizenCoddWebMaps/'
ttl_sec = 30 if not debug else 30

tz = pytz.timezone('Europe/Moscow')


class UserLoc(NamedTuple):
    lat: float
    lon: float


class BusStop(NamedTuple):
    NAME_: str
    LAT_: float
    LON_: float

    def __str__(self):
        return f'(BusStop: {self.NAME_} {self.LON_} {self.LAT_} )'

    def distance_km(self, bus_stop):
        return distance_km(self.LON, self.LAT_, bus_stop.LON_, bus_stop.LAT_,)


class LongBusRouteStop(NamedTuple):
    NUMBER_: int
    NAME_: str
    LAT_: float
    LON_: float
    ROUT_: int
    CONTROL_: int

    def distance_km(self, bus_stop):
        return distance_km(self.LAT_, self.LON_, bus_stop.LAT_, bus_stop.LON_)


class ShortBusRoute(NamedTuple):
    NUMBER_: int
    ROUT_: int
    CONTROL_: int
    STOPID: int


class CoddNextBus(NamedTuple):
    rname_: str
    time_: int


class CoddBus(NamedTuple):
    NAME_: str
    ID_: int


class CdsBus(NamedTuple):
    obj_id_: int
    proj_id_: int
    last_speed_: int
    last_lon_: float
    last_lat_: float
    name_: str
    last_time_: str
    route_name_: str
    type_proj: int
    phone_: str


class CoddRouteBus(NamedTuple):
    obj_id_: int
    proj_id_: int
    last_speed_: int
    last_lon_: float
    last_lat_: float
    lon2: int
    lat2: int
    azimuth: int
    last_time_: str
    route_name_: str
    type_proj: int
    lowfloor: int
    dist: int = 0


class CdsRouteBus(NamedTuple):
    last_lat_: float
    last_lon_: float
    last_speed_: float
    last_time_: str
    name_: str
    obj_id_: int
    proj_id_: int
    route_name_: str
    type_proj: int = 0
    bus_station_: str = None
    address: str = None

    def short(self):
        return f'{self.bus_station_}; {self.last_lat_} {self.last_lon_} '

    def distance(self, bus_stop=None, user_loc: UserLoc = None):
        if not bus_stop and not user_loc:
            return 10000
        (lat, lon) = (bus_stop.LON_, bus_stop.LAT_) if bus_stop else (user_loc.lat, user_loc.lon)
        return distance(lat, lon, self.last_lat_, self.last_lon_)

    def distance_km(self, bus_stop: BusStop = None, user_loc: UserLoc = None):
        (lat, lon) = (bus_stop.LON_, bus_stop.LAT_) if bus_stop else (user_loc.lat, user_loc.lon)
        return distance_km(lat, lon, self.last_lat_, self.last_lon_)


def init_bus_stops():
    with open('bus_stops.json', 'rb') as f:
        return json.load(f)


def init_bus_routes():
    with open(Path("bus_stations.json"), 'rb') as f:
        bus_stations = json.load(f)

    result = {}
    for k, v in bus_stations.items():
        route = [LongBusRouteStop(*i) for i in v]
        route.sort(key=lambda tup: tup.NUMBER_)
        result[k] = route

    return result


class CdsRequest:
    def __init__(self, logger: Logger):
        self.cookies = {'JSESSIONID': 'C8ED75C7EC5371CBE836BDC748BB298F', 'session_id': 'vrntrans'}
        self.logger = logger
        self.fake_header = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                          '(KHTML, like Gecko) Chrome/63.0.3239.132 Safari/537.36'}
        self.bus_stops = [BusStop(**i) for i in init_bus_stops()]
        self.bus_routes = init_bus_routes()
        self.cds_db = fdb.connect(host=CDS_HOST, database=CDS_DB_PATH, user=CDS_USER,
                                  password=CDS_PASS, charset='WIN1251')
        self.cds_db.default_tpb = fdb.ISOLATION_LEVEL_READ_COMMITED_RO
        self.cds_routes = self.init_cds_routes()
        self.codd_routes = self.init_codd_routes()

    def load_cds_bus_routes(self) -> {}:
        routes_base_local = {}
        cds_buses = self.get_cds_buses()
        for bus in cds_buses:
            if bus.proj_id_ and bus.route_name_:
                route = bus.route_name_
                if route not in routes_base_local:
                    routes_base_local[bus.route_name_] = bus.proj_id_
        with open('bus_routes_cds.json', 'wb') as f:
            json.dump(routes_base_local, codecs.getwriter('utf-8')(f), ensure_ascii=False, indent=4)
        return routes_base_local

    def load_codd_bus_routes(self) -> {}:
        routes_base_local = {}
        cds_buses = self.get_codd_buses()
        for bus in cds_buses:
            if bus.NAME_ and bus.ID_:
                route = bus.NAME_
                if route not in routes_base_local:
                    routes_base_local[bus.NAME_] = bus.ID_
        with open('bus_routes_codd.json', 'wb') as f:
            json.dump(routes_base_local, codecs.getwriter('utf-8')(f), ensure_ascii=False, indent=4)
        return routes_base_local

    def init_codd_routes(self) -> Dict:
        my_file = Path("bus_routes_codd.json")
        if my_file.is_file():
            with open(my_file, 'rb') as f:
                return json.load(f)
        else:
            return self.load_codd_bus_routes()

    def init_cds_routes(self):
        my_file = Path("bus_routes_cds.json")
        if my_file.is_file():
            with open(my_file, 'rb') as f:
                return json.load(f)
        else:
            return self.load_cds_bus_routes()

    @cachetools.func.ttl_cache()
    def matches_bus_stops(self, lat, lon, size=3):
        def distance_key(item):
            return distance(item.LAT_, item.LON_, lon, lat)

        return sorted(self.bus_stops, key=distance_key)[:size]

    @cachetools.func.ttl_cache(ttl=ttl_sec)
    def bus_request_as_list(self, bus_route):
        def key_check(route):
            return route.name_ and route.last_time_ and (now - get_time(route.last_time_)) < delta

        keys = set([x for x in self.cds_routes.keys() for r in bus_route if x.upper() == r.upper()])

        routes = self.load_cds_buses_from_db(tuple(keys))
        self.logger.debug(routes)
        if routes:
            now = datetime.now(tz=tz)
            delta = timedelta(days=1)
            short_result = sorted([d for d in routes if key_check(d)],
                                  key=lambda s: natural_sort_key(s.route_name_))
            return short_result
        return []

    @cachetools.func.ttl_cache(maxsize=1024)
    def get_closest_bus_stop(self, bus_info: CdsRouteBus, strict=False):
        bus_stop = next((x for x in self.bus_stops if x.NAME_ == bus_info.bus_station_), None)
        if bus_stop:
            if bus_info.distance(bus_stop) < 0.015:
                return bus_stop

        if strict:
            bus_stops = self.bus_routes.get(bus_info.route_name_, [])
            result = min(bus_stops, key=bus_info.distance)
        else:
            result = min(self.bus_stops, key=bus_info.distance)
        if not bus_info.bus_station_:
            self.logger.debug(f"Empty station: {bus_info.short()} {result}")
            return result

        if bus_stop:
            d1 = bus_info.distance(bus_stop)
            d2 = bus_info.distance(result)
            if d2 > d1:
                self.logger.debug(f"Original: {bus_info.short()}; "
                                  "By name: {bus_stop}, Closests: {result}, {d1} {d2}")
                return bus_stop

        return result

    @cachetools.func.ttl_cache()
    def bus_station(self, bus_info: CdsRouteBus, strict=False):
        result = self.get_closest_bus_stop(bus_info, strict)
        if not result.NAME_:
            self.logger.error(f"{result} {bus_info}")
        return result.NAME_

    def station(self, d: CdsRouteBus, show_route_name=True, user_loc: UserLoc = None, full_info=False):
        bus_station = self.bus_station(d)
        dist = f'{(d.distance_km(user_loc=user_loc)):.1f} км' if user_loc else ''
        route_name = f"{d.route_name_} " if show_route_name else ""
        result = f"{route_name}{get_time(d.last_time_):%H:%M} {bus_station} {dist}"
        if full_info:
            orig_bus_stop = ""
            if not bus_station == d.bus_station_:
                orig_bus_stop = (' | ' + str(d.bus_station_))
            return f"{result} {d.name_}{orig_bus_stop}"
        return result

    def filter_bus_list(self, bus_list, bus_filter='', full_info=False):
        def time_check(d: CdsRouteBus, now, delta):
            return d.last_time_ and (now - get_time(d.last_time_)) < delta

        def filtered(d: CdsRouteBus, bus_filter):
            return bus_filter == '' or bus_filter in d.name_

        now = datetime.now(tz=tz)
        delta = timedelta(minutes=30)
        stations_filtered = [(d, self.get_next_bus_stop(d.route_name_, self.bus_station(d, True))) for d in
                             bus_list if
                             filtered(d, bus_filter) and (full_info or time_check(d, now, delta))]
        return stations_filtered

    @cachetools.func.ttl_cache(ttl=ttl_sec)
    def bus_request(self, full_info=False, bus_route=tuple(), bus_filter='',
                    user_loc: UserLoc = None, short_format=False):
        keys = set([x for x in self.cds_routes.keys() for r in bus_route if x.upper() == r.upper()])

        if not keys and bus_filter == '':
            return 'Не заданы маршруты', []
        short_result = self.bus_request_as_list(tuple(keys))
        if short_result:
            stations_filtered = self.filter_bus_list(short_result, bus_filter, full_info)
            if stations_filtered:
                stations_filtered.sort(key=lambda x: natural_sort_key(x[0].route_name_))
                if short_format:
                    lines = []
                    cur_route = ''
                    for (k, v) in stations_filtered:
                        if cur_route != k.route_name_:
                            cur_route = k.route_name_
                            lines.append("")
                            lines.append(cur_route)
                        lines.append(self.station(k, False, full_info=full_info, user_loc=user_loc))
                    text = ' \n'.join(lines)
                else:
                    text = ' \n'.join((self.station(d[0], full_info=full_info, user_loc=user_loc)
                                       for d in stations_filtered))
                return text, stations_filtered

        return 'Ничего не нашлось', []

    @cachetools.func.ttl_cache(ttl=ttl_sec * 1.5)
    @retry_multi()
    def next_bus_for_lat_lon(self, lat, lon) -> Iterable[CoddNextBus]:
        url = f'{codd_base_usl}GetNextBus'
        payload = {'lat': lat, 'lon': lon}
        r = requests.post(url, data=payload, headers=self.fake_header)
        self.logger.info(f"{r.url} {payload} {r.elapsed} {len(r.text)}")
        text = r.text
        if not text:
            raise Exception(f"Should be result for next_bus_for_lat_lon {lat} {lon}")

        self.logger.debug(f'Response: {text}')
        result = [CoddNextBus(**i) for i in self.json_fix_and_load(text) if i]
        return result

    @cachetools.func.ttl_cache(ttl=ttl_sec)
    @retry_multi()
    def load_cds_buses(self, keys):
        routes = [{'proj_ID': self.cds_routes.get(k), 'route': k} for k in keys]
        if not routes:
            return []
        payload = {'routes': json.dumps(routes)}
        self.logger.info(f"bus_request_as_list {routes}")
        url = f'{cds_url_base}GetRouteBuses'
        r = requests.post(url, cookies=self.cookies, data=payload, headers=self.fake_header)
        self.logger.info(f"{r.url} {payload} {r.elapsed} {len(r.text)/1024:.2f} kB")
        if len(r.text) == 0:
            self.logger.warning(r)
            raise Exception(f"Should be result for {keys}")

        if r.text:
            return [CdsRouteBus(**i) for i in self.json_fix_and_load(r.text)]
        return []

    @cachetools.func.ttl_cache(ttl=ttl_sec)
    @retry_multi()
    def load_all_cds_buses_from_db(self) -> Iterable[CdsRouteBus]:
        def make_names_lower(x):
            return {k.lower(): v for (k, v) in x.iteritems()}

        self.logger.info('Execute fetch all from DB')
        start = time.time()
        with fdb.TransactionContext(self.cds_db):
            cur = self.cds_db.cursor()
            cur.execute('''SELECT bs.NAME_ AS BUS_STATION_, rt.NAME_ AS ROUTE_NAME_,  o.NAME_, o.OBJ_ID_, o.LAST_TIME_,
                o.LAST_LON_, o.LAST_LAT_, o.LAST_SPEED_, o.PROJ_ID_
                FROM OBJECTS O JOIN BUS_STATIONS bs
                ON o.LAST_ROUT_ = bs.ROUT_ AND o.LAST_STATION_ = bs.NUMBER_
                JOIN ROUTS rt ON o.LAST_ROUT_ = rt.ID_
                WHERE obj_output_=0''')
            self.logger.info('Finish execution')
            result = cur.fetchallmap()
            cur.close()
            end = time.time()
            self.logger.info(f"Finish fetch. Elapsed: {end - start:.2f}")

        result = [CdsRouteBus(**make_names_lower(x)) for x in result]
        result.sort(key=lambda s: s.last_time_, reverse=True)
        end = time.time()
        self.logger.info(f"Finish proccess. Elapsed: {end - start:.2f}")
        return result

    @cachetools.func.ttl_cache(ttl=ttl_sec)
    @retry_multi()
    def load_cds_buses_from_db(self, keys):
        all_buses = self.load_all_cds_buses_from_db()
        if not keys:
            return all_buses
        result = (x for x in all_buses if x.route_name_ in keys)
        return result

    @cachetools.func.ttl_cache(ttl=ttl_sec * 1.5)
    def next_bus(self, bus_stop, user_bus_list):
        bus_stop = ' '.join(bus_stop)
        bus_stop_matches = [x for x in self.bus_stops if bus_stop.upper() in x.NAME_.upper()]
        print(bus_stop, bus_stop_matches)
        if not bus_stop_matches:
            return f'Остановки c именем "{bus_stop}" не найдены'
        if len(bus_stop_matches) > 5:
            first_matches = '\n'.join([x.NAME_ for x in bus_stop_matches[:20]])
            return f'Уточните остановку. Найденные варианты:\n{first_matches}'
        return self.next_bus_for_matches(bus_stop_matches, user_bus_list)[0]

    # @cachetools.func.ttl_cache(ttl=60)
    def next_bus_for_matches(self, bus_stop_matches, user_bus_list):
        result = []
        routes_set = set()
        if user_bus_list:
            result.append(f"Фильтр по маршрутам: {' '.join(user_bus_list)}. Настройка: /settings")
        for item in bus_stop_matches:
            arrivals = self.next_bus_for_lat_lon(item.LAT_, item.LON_)
            if arrivals:
                header = arrivals[0]
                items = [x for x in arrivals[1:] if
                         x.time_ > 0 and (not user_bus_list or x.rname_.strip() in user_bus_list)]
                routes_set.update([x.rname_.strip() for x in items])
                self.logger.info(items)
                items.sort(key=lambda s: natural_sort_key(s.rname_))
                if not items:
                    result.append(f'Остановка {header.rname_}: нет данных')
                    continue
                next_bus_info = f"Остановка {header.rname_}:\n"
                next_bus_info += '\n'.join((f"{x.rname_} - {x.time_} мин" for x in items))
                result.append(next_bus_info)
        routes_list = list(routes_set)
        routes_list.sort(key=natural_sort_key)
        result.append(f'Ожидаемые маршруты (но это не точно, проверьте список): {" ".join(routes_list)}')
        return ('\n'.join(result), " ".join(routes_list))

    def get_bus_distance_to(self, bus_route_names, bus_stop_name):
        result = []
        all_buses = self.load_cds_buses_from_db(tuple(bus_route_names))
        for bus in all_buses:
            dist = self.get_dist(bus.route_name_, bus.bus_station_, bus_stop_name)
            if dist > 0 and dist < 50:
                result.append((bus, dist))
        return result

    # @cachetools.func.ttl_cache(ttl=60)
    def next_bus_for_matches_alt(self, bus_stop_matches, user_bus_list):
        result = []
        routes_set = set()
        if user_bus_list:
            result.append(f"Фильтр по маршрутам: {' '.join(user_bus_list)}. Настройка: /settings")
        for item in bus_stop_matches:
            arrival_buses = self.get_routes_on_bus_stop(item.NAME_)
            arrival_buses = [x for x in arrival_buses if not user_bus_list or x in user_bus_list]
            if not arrival_buses:
                continue
            routes_set.update(arrival_buses)
            arrival_buses.sort(key=natural_sort_key)
            result.append(f'{item.NAME_}: {", ".join(arrival_buses)}')
            distance_list = self.get_bus_distance_to(arrival_buses, item.NAME_)
            distance_list.sort(key=lambda x: x[1])
            result.append('\n'.join((f'{d[0].route_name_} {d[1]:.2f} км {d[0].bus_station_}' for d in distance_list )))
        routes_list = list(routes_set)
        routes_list.sort(key=natural_sort_key)
        result.append(f'Ожидаемые маршруты (но это не точно, проверьте список): {" ".join(routes_list)}')
        return ('\n'.join(result), " ".join(routes_list))


    @cachetools.func.ttl_cache(ttl=30)
    @retry_multi(max_retries=5)
    def get_cds_buses(self) -> Iterable[CdsBus]:
        r = requests.get(f'{cds_url_base}GetBuses', cookies=self.cookies, headers=self.fake_header)
        self.logger.info(f"{r.url} {r.elapsed} {len(r.text)}")
        if not r.text:
            raise Exception("Should be results")
        result: Iterable[CdsBus] = [CdsBus(**i) for i in self.json_fix_and_load(r.text) if 'User' not in i]
        return result

    @cachetools.func.ttl_cache(ttl=30)
    @retry_multi(max_retries=5)
    def get_codd_buses(self) -> Iterable[CoddBus]:
        r = requests.get(f'{codd_base_usl}GetBusesServlet', headers=self.fake_header)
        self.logger.info(f"{r.url} {r.elapsed} {len(r.text)}")
        if not r.text:
            raise Exception("Should be results")
        result: Iterable[CoddBus] = [CoddBus(**i) for i in self.json_fix_and_load(r.text)]
        return result

    @cachetools.func.ttl_cache()
    def get_all_buses(self):
        def key_check(x: CdsBus):
            return x.name_ and x.last_time_ and (now - get_time(x.last_time_)) < hour

        cds_buses = self.load_all_cds_buses_from_db()
        if not cds_buses:
            return 'Ничего не нашлось'

        now = datetime.now(tz=tz)
        hour = timedelta(hours=1)
        short_result = [(d.name_, d.last_time_, d.route_name_, d.proj_id_) for d in cds_buses if
                        key_check(d)]
        short_result = sorted(short_result, key=lambda x: natural_sort_key(x[2]))
        grouped = [(k, len(list(g))) for k, g in groupby(short_result, lambda x: f'{x[2]} ({x[3]})')]
        if short_result:
            buses = ' \n'.join((('{} => {}'.format(i[0], i[1])) for i in grouped))
            return buses

        return 'Ничего не нашлось'

    @cachetools.func.ttl_cache(ttl=ttl_sec)
    @retry_multi()
    def load_codd_buses(self, bus_route) -> Iterable[CoddRouteBus]:
        keys = set([x for x in self.codd_routes.keys() for r in bus_route if x.upper() == r.upper()])
        routes = [{'proj_ID': self.codd_routes.get(k), 'route': k} for k in keys]
        if not routes:
            return []
        payload = {'routes': json.dumps(routes)}
        self.logger.info(f"bus_request_as_list {routes}")
        url = f'{codd_base_usl}GetRouteBuses'
        r = requests.post(url, data=payload, headers=self.fake_header)
        self.logger.info(f"{r.url} {payload} {r.elapsed} {len(r.text)/1024:.2} kB")
        if len(r.text) == 0 or r.text == '[,]':
            self.logger.warning(f'Empty or wrong result: {r}')
            # raise Exception(f"Should be result for {keys}")
            return []
        if r.text:
            return [CoddRouteBus(**i) for i in self.json_fix_and_load(r.text)]
        return []

    def json_fix_and_load(self, text: str):
        if ',,' in text:
            text = text.replace(',,', ',')
        if '[,' in text:
            text = text.replace('[,', '[')
        if ',]' in text:
            text = text.replace(',]', ']')

        try:
            json_object = json.loads(text)
        except ValueError as e:
            self.logger.warning(f'Exception {e}')
            self.logger.warning(f'Wrong parse {text}')
            return []
        return json_object

    def get_dist(self, route_name, bus_stop_start, bus_stop_stop):
        route: Iterable[LongBusRouteStop] = self.bus_routes.get(route_name, [])
        dist = 0
        prev_stop = None
        for bus_stop in route:
            if prev_stop:
                dist += prev_stop.distance_km(bus_stop)
                prev_stop = bus_stop
            if not prev_stop and bus_stop.NAME_ == bus_stop_start:
                prev_stop = bus_stop
            if bus_stop.NAME_ == bus_stop_stop:
                break
        return dist

    def get_routes_on_bus_stop(self, bus_stop_name):
        result = []
        for (k, v) in self.bus_routes.items():
            if next((True for x in v if x.NAME_ == bus_stop_name), False):
                result.append(k)
        return result

    def get_next_bus_stop(self, route_name, bus_stop_name):
        route = self.bus_routes.get(route_name, [])
        if not route:
            self.logger.info(self.bus_routes)
            self.logger.error(f"Wrong params {route_name}, {bus_stop_name}. Didn't find anything")
            return
        size = len(route)
        for (i, v) in enumerate(route):
            if v.NAME_ == bus_stop_name:
                if (i + 2) < size:
                    return route[i + 1]
                if i + 1 == size:
                    return v
                return v
        self.logger.error(f"Wrong params {route_name}, {bus_stop_name}")
        bus_stop = next((x for x in self.bus_stops if x.NAME_ == bus_stop_name), None)
        if bus_stop:
            return bus_stop
        else:
            self.logger.error(f"Cannot found {bus_stop_name}, will return first bus_stop")
            return self.bus_stops[0]
