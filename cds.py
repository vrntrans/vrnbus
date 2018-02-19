import codecs
import heapq
import json
import os
import time
from collections import Counter, deque
from collections import defaultdict
from datetime import datetime, timedelta
from itertools import groupby, product
from logging import Logger
from pathlib import Path
from typing import NamedTuple, Iterable, Dict, List, Container

import cachetools.func
import fdb
import pytz
import requests

from helpers import get_iso_time, fuzzy_search_advanced
from helpers import get_time, natural_sort_key, distance, distance_km, retry_multi, SearchResult

LOAD_TEST_DATA = False

try:
    import settings

    CDS_HOST = settings.CDS_HOST
    CDS_DB_PATH = settings.CDS_DB_PATH
    CDS_USER = settings.CDS_USER
    CDS_PASS = settings.CDS_PASS
    LOAD_TEST_DATA = settings.LOAD_TEST_DATA
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
ttl_sec = 30 if not LOAD_TEST_DATA else 0.001
ttl_db_sec = 30 if not LOAD_TEST_DATA else 0.001

tz = pytz.timezone('Europe/Moscow')


class ArrivalInfo(NamedTuple):
    text: str
    header: str = ''
    bus_stops: dict = {}


class UserLoc(NamedTuple):
    lat: float
    lon: float


class BusStop(NamedTuple):
    NAME_: str
    LAT_: float
    LON_: float

    def __str__(self):
        return f'(BusStop: {self.NAME_} {self.LAT_} {self.LON_}  )'

    def distance_km(self, bus_stop):
        return distance_km(self.LAT_, self.LON_, bus_stop.LAT_, bus_stop.LON_)


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


class CdsBusPosition(NamedTuple):
    last_lat: float
    last_lon: float
    last_time: datetime

    def distance(self, bus_stop: BusStop = None, user_loc: UserLoc = None):
        if not bus_stop and not user_loc:
            return 10000

        (lat, lon) = (bus_stop.LAT_, bus_stop.LON_) if bus_stop else (user_loc.lat, user_loc.lon)
        return distance(lat, lon, self.last_lat, self.last_lon)

    def distance_km(self, bus_stop: BusStop = None, user_loc: UserLoc = None):
        (lat, lon) = (bus_stop.LAT_, bus_stop.LON_) if bus_stop else (user_loc.lat, user_loc.lon)
        return distance_km(lat, lon, self.last_lat, self.last_lon)


class CdsRouteBus(NamedTuple):
    last_lat_: float
    last_lon_: float
    last_speed_: float
    last_time_: datetime
    name_: str
    obj_id_: int
    proj_id_: int
    route_name_: str
    type_proj: int = 0
    last_station_time_: datetime = None
    bus_station_: str = None
    address: str = None

    @staticmethod
    def make(last_lat_, last_lon_, last_speed_, last_time_, name_, obj_id_, proj_id_, route_name_,
             type_proj, last_station_time_, bus_station_, address):
        last_time_ = get_iso_time(last_time_)
        last_station_time_ = get_iso_time(last_station_time_)
        return CdsRouteBus(last_lat_, last_lon_, last_speed_, last_time_, name_, obj_id_, proj_id_,
                           route_name_, type_proj, last_station_time_, bus_station_, address)

    def get_bus_position(self) -> CdsBusPosition:
        return CdsBusPosition(self.last_lat_, self.last_lon_, self.last_time_)

    def short(self):
        return f'{self.bus_station_}; {self.last_lat_} {self.last_lon_} '

    def distance(self, bus_stop: BusStop = None, user_loc: UserLoc = None):
        if not bus_stop and not user_loc:
            return 10000
        (lat, lon) = (bus_stop.LAT_, bus_stop.LON_) if bus_stop else (user_loc.lat, user_loc.lon)
        return distance(lat, lon, self.last_lat_, self.last_lon_)

    def distance_km(self, bus_stop: BusStop = None, user_loc: UserLoc = None):
        (lat, lon) = (bus_stop.LAT_, bus_stop.LON_) if bus_stop else (user_loc.lat, user_loc.lon)
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
        self.fake_header = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                                          '(KHTML, like Gecko) Chrome/63.0.3239.132 Safari/537.36'}
        self.bus_stops = [BusStop(**i) for i in init_bus_stops()]
        self.bus_routes = init_bus_routes()
        if not LOAD_TEST_DATA:
            self.cds_db = fdb.connect(host=CDS_HOST, database=CDS_DB_PATH, user=CDS_USER,
                                      password=CDS_PASS, charset='WIN1251')
            self.cds_db.default_tpb = fdb.ISOLATION_LEVEL_READ_COMMITED_RO
        else:
            self.test_data_files = []
            self.test_data_index = 0
            self.mocked_now = datetime.now()
            self.load_test_data()
        self.cds_routes = self.init_cds_routes()
        self.codd_routes = self.init_codd_routes()
        self.avg_speed = 18.0
        self.last_bus_data = defaultdict(lambda: deque(maxlen=10))
        self.speed_dict = {}
        self.speed_deque = deque(maxlen=10)

    def get_last_bus_data(self, bus_name):
        return self.last_bus_data.get(bus_name)

    def add_last_bus_data(self, bus_name, bus_data):
        value = self.last_bus_data[bus_name]
        if bus_data in value:
            return
        value.append(bus_data)

    def load_test_data(self):
        self.test_data_files = sorted(Path('./test_data/').glob('codd_data_db*.json'))
        self.test_data_index = 0
        if self.test_data_files:
            path = self.test_data_files[0]
            self.mocked_now = datetime.strptime(path.name, "codd_data_db%y_%m_%d_%H_%M_%S.json")
        else:
            self.logger.error("Cannot load test data from ./test_data/")

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
            return distance(item.LAT_, item.LON_, lat, lon)

        return sorted(self.bus_stops, key=distance_key)[:size]

    @cachetools.func.ttl_cache(ttl=ttl_sec)
    def bus_request_as_list(self, bus_routes):
        def key_check(route: CdsRouteBus):
            return route.name_ and route.last_time_ and (now - route.last_time_) < delta

        keys = set([x for x in self.cds_routes.keys() for r in bus_routes if x.upper() == r.upper()])

        routes = self.load_cds_buses_from_db(tuple(keys))
        self.logger.debug(routes)
        if routes:
            now = self.now()
            delta = timedelta(days=7)
            short_result = sorted([d for d in routes if key_check(d)],
                                  key=lambda s: natural_sort_key(s.route_name_))
            return short_result
        return []

    def get_closest_bus_stop_checked(self, route_name: str, bus_positions: Container[CdsBusPosition]):
        bus_stops = self.bus_routes.get(route_name, [])

        if not bus_stops:
            raise Exception(f"Empty bus_stops for {route_name}")

        if not bus_positions:
            raise Exception("Empty bus_positions for {route_name}")

        last_position = bus_positions[-1]

        (curr_1, curr_2) = heapq.nsmallest(2, bus_stops, key=last_position.distance)
        if curr_1.NUMBER_ == curr_2.NUMBER_ + 1:
            return curr_1
        elif curr_2.NUMBER_ == curr_1.NUMBER_ + 1:
            return curr_2

        m_num = bus_stops[len(bus_stops) // 2].NUMBER_
        curr_pos = {curr_1, curr_2}
        bus_positions = list(bus_positions)
        for prev_position in bus_positions[-1::-1]:
            closest_prev = heapq.nsmallest(2, bus_stops, key=prev_position.distance)
            if set(closest_prev) == curr_pos:
                continue

            all_cases = product((curr_1, curr_2), closest_prev)
            for (s1, s2) in all_cases:
                n1, n2 = s1.NUMBER_, s2.NUMBER_
                if n1 > n2 and ((n1 <= m_num and n2 <= m_num) or (n1 >= m_num and n2 >= m_num)):
                    return s1

            self.logger.warning(f"Didn't find correct bus stop for {last_position}")

        return curr_1

    @cachetools.func.ttl_cache(ttl=ttl_sec, maxsize=2048)
    def get_closest_bus_stop(self, bus_info: CdsRouteBus, strict=False):
        bus_stop = next((x for x in self.bus_stops
                         if bus_info.bus_station_ and x.NAME_ == bus_info.bus_station_), None)
        if bus_stop and bus_info.distance(bus_stop) < 0.015:
            return bus_stop

        if strict:
            bus_positions = self.last_bus_data[bus_info.name_]
            result = self.get_closest_bus_stop_checked(bus_info.route_name_, bus_positions)
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

    @cachetools.func.ttl_cache(ttl=ttl_sec)
    def bus_station(self, bus_info: CdsRouteBus, strict=False):
        result = self.get_closest_bus_stop(bus_info, strict)
        if not result.NAME_:
            self.logger.error(f"{result} {bus_info}")
        return result.NAME_

    def station(self, d: CdsRouteBus, user_loc: UserLoc = None, full_info=False, show_route_name=True):
        bus_station = self.bus_station(d, True)
        dist = f'{(d.distance_km(user_loc=user_loc)):.1f} км' if user_loc else ''
        route_name = f"{d.route_name_} " if show_route_name else ""
        day_info = ""
        if self.now() - d.last_time_ > timedelta(days=1):
            day_info = f'{d.last_time_:%d.%m} '
        result = f"{route_name}{day_info}{get_time(d.last_time_):%H:%M} {bus_station} {dist}"
        if full_info:
            orig_bus_stop = ""
            if not bus_station == d.bus_station_:
                orig_bus_stop = (' | ' + str(d.bus_station_))

            return f"{result} {d.name_}{orig_bus_stop}"
        return result

    def filter_bus_list(self, bus_list, search_result: SearchResult):
        def time_check(d: CdsRouteBus):
            if search_result.full_info:
                return True
            return d.last_time_ and (now - d.last_time_) < delta

        def filtered(d: CdsRouteBus):
            return search_result.bus_filter == '' or search_result.bus_filter in d.name_

        now = self.now()
        delta = timedelta(minutes=30)
        stations_filtered = [(d, self.get_next_bus_stop(d.route_name_, self.bus_station(d, True)))
                             for d in bus_list if filtered(d) and time_check(d)]
        return stations_filtered

    @cachetools.func.ttl_cache(ttl=ttl_sec)
    def bus_request(self, search_result: SearchResult, user_loc: UserLoc = None, short_format=False):
        keys = set([x for x in self.cds_routes.keys()
                    for r in search_result.bus_routes if x.upper() == r.upper()])

        if not keys and search_result.bus_filter == '':
            return 'Не заданы маршруты', []
        short_result = self.bus_request_as_list(tuple(keys))
        if short_result:
            stations_filtered = self.filter_bus_list(short_result, search_result)
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
                        lines.append(self.station(k, user_loc, search_result.full_info, False))
                    text = ' \n'.join(lines)
                else:
                    text = ' \n'.join((self.station(d[0], user_loc, search_result.full_info)
                                       for d in stations_filtered))
                return text, stations_filtered

        return 'Ничего не нашлось', []

    @cachetools.func.ttl_cache(ttl=ttl_sec * 1.5)
    @retry_multi()
    def next_bus_for_lat_lon(self, lat, lon) -> List[CoddNextBus]:
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

    def now(self):
        if LOAD_TEST_DATA:
            if self.test_data_files and self.test_data_index >= len(self.test_data_files):
                self.test_data_index = 0
            path = self.test_data_files[self.test_data_index]
            self.mocked_now = datetime.strptime(path.name, "codd_data_db%y_%m_%d_%H_%M_%S.json")
            return self.mocked_now
        return datetime.now()

    def next_test_data(self):
        if self.test_data_files and self.test_data_index >= len(self.test_data_files):
            self.test_data_index = 0
        path = self.test_data_files[self.test_data_index]
        self.mocked_now = datetime.strptime(path.name, "codd_data_db%y_%m_%d_%H_%M_%S.json")
        with open(path, 'rb') as f:
            long_bus_stops = [CdsRouteBus.make(*i) for i in json.load(f)]
        self.test_data_index += 1
        self.logger.info(f'Loaded {path.name}; {self.mocked_now:%H:%M:%S}')
        return long_bus_stops

    @cachetools.func.ttl_cache(ttl=ttl_db_sec)
    @retry_multi()
    def load_all_cds_buses_from_db(self) -> Iterable[CdsRouteBus]:
        def update_last_bus_data(buses):
            for bus in buses:
                self.add_last_bus_data(bus.name_, bus.get_bus_position())

        def make_names_lower(x):
            return {k.lower(): v for (k, v) in x.iteritems()}

        if LOAD_TEST_DATA:
            data = self.next_test_data()
            update_last_bus_data(data)
            return data

        self.logger.info('Execute fetch all from DB')
        start = time.time()
        try:
            with fdb.TransactionContext(self.cds_db.trans(fdb.ISOLATION_LEVEL_READ_COMMITED_RO)) as tr:
                cur = tr.cursor()
                cur.execute('''SELECT bs.NAME_ AS BUS_STATION_, rt.NAME_ AS ROUTE_NAME_,  o.NAME_, o.OBJ_ID_, o.LAST_TIME_,
                    o.LAST_LON_, o.LAST_LAT_, o.LAST_SPEED_, o.LAST_STATION_TIME_, o.PROJ_ID_
                    FROM OBJECTS O JOIN BUS_STATIONS bs
                    ON o.LAST_ROUT_ = bs.ROUT_ AND o.LAST_STATION_ = bs.NUMBER_
                    JOIN ROUTS rt ON o.LAST_ROUT_ = rt.ID_
                    WHERE obj_output_=0''')
                self.logger.info('Finish execution')
                result = cur.fetchallmap()
                tr.commit()
                cur.close()
                end = time.time()
                self.logger.info(f"Finish fetch. Elapsed: {end - start:.2f}")
        except fdb.fbcore.DatabaseError as db_error:
            self.logger.error(db_error)
            try:
                self.cds_db = fdb.connect(host=CDS_HOST, database=CDS_DB_PATH, user=CDS_USER,
                                          password=CDS_PASS, charset='WIN1251')
                self.cds_db.default_tpb = fdb.ISOLATION_LEVEL_READ_COMMITED_RO
            except Exception as general_error:
                self.logger.error(general_error)
            return []

        result = [CdsRouteBus(**make_names_lower(x)) for x in result]
        update_last_bus_data(result)
        result.sort(key=lambda s: s.last_time_, reverse=True)
        end = time.time()
        self.logger.info(f"Finish proccess. Elapsed: {end - start:.2f}")
        return result

    @cachetools.func.ttl_cache(ttl=ttl_sec)
    def calc_avg_speed(self):
        def time_filter(bus: CdsRouteBus):
            if not bus.last_time_ or bus.last_time_ < last_n_minutes:
                return False
            if bus.last_station_time_ and bus.last_station_time_ < last_n_minutes:
                return False
            return True

        bus_full_list = self.load_all_cds_buses_from_db()
        now = self.now()
        last_n_minutes = now - timedelta(minutes=15)
        bus_list = list(filter(time_filter, bus_full_list))
        self.logger.info(f'Buses in last 15 munutes {len(bus_list)} from {len(bus_full_list)}')
        sum_speed = sum((x.last_speed_ for x in bus_list))
        if len(bus_list) > 0:
            self.speed_deque.append(sum_speed * 1.0 / len(bus_list))
            self.avg_speed = sum(self.speed_deque) / len(self.speed_deque)
        self.logger.info(f'Average speed for all buses: {self.avg_speed:.1f}')
        speed_dict = {}
        curr_bus_routes = Counter((x.route_name_ for x in bus_list))
        for (route, size) in curr_bus_routes.items():
            speed_dict[route] = sum((x.last_speed_ for x in bus_list if x.route_name_ == route)) / size
        self.speed_dict = speed_dict

    @cachetools.func.ttl_cache(ttl=ttl_sec)
    @retry_multi()
    def load_cds_buses_from_db(self, keys) -> Iterable[CdsRouteBus]:
        all_buses = self.load_all_cds_buses_from_db()
        if not keys:
            return all_buses
        result = [x for x in all_buses if x.route_name_ in keys]
        return result

    @cachetools.func.ttl_cache(ttl=ttl_sec)
    def next_bus(self, bus_stop_query, search_result, alt=True) -> ArrivalInfo:
        bus_stop_matches = [x for x in self.bus_stops if fuzzy_search_advanced(bus_stop_query, x.NAME_)]
        if not bus_stop_matches:
            text = f'Остановки c именем "{bus_stop_query}" не найдены'
            return ArrivalInfo(text=text, header=text)
        if len(bus_stop_matches) > 5:
            first_matches = '\n'.join([x.NAME_ for x in bus_stop_matches[:20]])
            bus_stop_dict = {x.NAME_: '' for x in bus_stop_matches[:20]}
            return ArrivalInfo(f'Уточните остановку. Найденные варианты:\n{first_matches}',
                               'Уточните остановку. Найденные варианты:', bus_stop_dict)
        method = self.next_bus_for_matches_alt if alt else self.next_bus_for_matches
        return method(tuple(bus_stop_matches), search_result)

    # @cachetools.func.ttl_cache(ttl=60)
    def next_bus_for_matches(self, bus_stop_matches, search_result: SearchResult):
        def show_arrival(info: CoddNextBus):
            routes = search_result.bus_routes
            return info.time_ > 0 and (not routes or info.rname_.strip() in routes)

        result = [f'Время: {self.now():%H:%M} (Рассчёт ЦОДД)']
        routes_set = set()
        if search_result.bus_routes:
            result.append(f"Фильтр по маршрутам: {' '.join(search_result.bus_routes)}")
        bus_stop_dict = {}
        headers = result[:]
        for item in bus_stop_matches:
            arrivals = self.next_bus_for_lat_lon(item.LAT_, item.LON_)
            if arrivals:
                header = arrivals[0]
                items = [x for x in arrivals[1:] if
                         show_arrival(x)]
                routes_set.update([x.rname_.strip() for x in items])
                self.logger.info(items)
                items.sort(key=lambda s: natural_sort_key(s.rname_))
                if not items:
                    result.append(f'Остановка {header.rname_}: нет данных')
                    bus_stop_dict[header.rname_] = ""
                    continue
                next_bus_info = f"Остановка {header.rname_}:\n"
                bus_stop_value = '\n'.join((f"{x.rname_:>5} {x.time_:>2.0f} мин" for x in items))
                next_bus_info += bus_stop_value
                bus_stop_dict[header.rname_] = bus_stop_value
                result.append(next_bus_info)
        routes_list = list(routes_set)
        routes_list.sort(key=natural_sort_key)
        result.append(f'Ожидаемые маршруты (но это не точно, проверьте список): {" ".join(routes_list)}')
        return ('\n'.join(result), "\n".join(headers), bus_stop_dict)

    @cachetools.func.ttl_cache(ttl=ttl_sec, maxsize=4096)
    def get_bus_distance_to(self, bus_route_names, bus_stop_name, bus_filter):
        def time_filter(bus_info: CdsRouteBus):
            if not bus_info.last_time_ or bus_info.last_time_ < last_n_minutes:
                return False
            if bus_info.last_station_time_ and bus_info.last_station_time_ < last_n_minutes:
                return False
            return True

        def time_to_arrive(km, last_time):
            speed = self.avg_speed if self.avg_speed > 0.1 else 0.1
            minutes = (km * 60 / speed)
            time_diff = now - last_time
            return minutes - time_diff.seconds / 60

        now = self.now()
        last_n_minutes = now - timedelta(minutes=15)

        result = []
        all_buses = [x for x in self.load_cds_buses_from_db(tuple(bus_route_names)) if time_filter(x)]
        if not all_buses:
            return result

        for bus in all_buses:
            if bus_filter and bus_filter not in bus.name_:
                continue
            closest_stop = self.get_closest_bus_stop(bus, True)
            bus_dist = bus.distance_km(closest_stop)
            same_station = bus.bus_station_ == bus_stop_name
            route_dist = self.get_dist(bus.route_name_, closest_stop.NAME_, bus_stop_name)
            if bus.bus_station_ != closest_stop.NAME_:
                route_dist += self.get_dist(bus.route_name_, bus.bus_station_, bus_stop_name)
            dist = bus_dist + route_dist
            time_left = time_to_arrive(dist, bus.last_time_)
            if (same_station or route_dist > 0) and dist < 20 and time_left < 30:
                result.append((bus, dist, time_left))
        return result

    # @cachetools.func.ttl_cache(ttl=30)
    def next_bus_for_matches_alt(self, bus_stop_matches, search_result: SearchResult) -> ArrivalInfo:
        def bus_info(bus: CdsRouteBus, distance, time_left):
            arrival_time = f"{time_left:>2.0f} мин" if time_left >= 1 else "ждём"
            info = f'{bus.route_name_:>5} {arrival_time}'
            if search_result.full_info:
                info += f' {distance:.2f} км {bus.last_time_:%H:%M} {bus.name_} {self.bus_station(bus, True)}'
            return info

        result = [f'Время: {self.now():%H:%M:%S}']
        routes_set = set()
        routes_filter = list(set([x for x in self.cds_routes.keys()
                                  for r in search_result.bus_routes if x.upper() == r.upper()]))
        self.calc_avg_speed()

        if search_result.bus_routes:
            result.append(f"Фильтр по маршрутам: {' '.join(search_result.bus_routes)};")
        if search_result.full_info:
            result.append(f"Средняя скорость: {self.avg_speed:2.1f} км/ч")
            if search_result.bus_routes and routes_filter:
                avg_speed_routes = sum((self.speed_dict.get(x, self.avg_speed)
                                        for x in routes_filter)) / len(routes_filter)

                result.append(f"Средняя скорость на маршрутах {avg_speed_routes:.2f} км/ч")

        bus_stop_dict = {}
        headers = result[:]
        for item in bus_stop_matches:
            arrival_buses = self.get_routes_on_bus_stop(item.NAME_)
            arrival_buses = [x for x in arrival_buses if not routes_filter or x in routes_filter]
            if not arrival_buses:
                continue
            if routes_filter:
                avg_speed_routes = sum((self.speed_dict.get(x, self.avg_speed)
                                        for x in routes_filter)) / len(routes_filter)
                self.logger.info(f'Average speed on routes {arrival_buses} {avg_speed_routes:.2f} kmh')

            routes_set.update(arrival_buses)
            arrival_buses = tuple(arrival_buses.sorted(key=natural_sort_key))
            result.append(f'{item.NAME_}:')
            distance_list = self.get_bus_distance_to(arrival_buses, item.NAME_, search_result.bus_filter)
            distance_list.sort(key=lambda x: x[2])
            bus_stop_value = '\n'.join((bus_info(*d) for d in distance_list))
            bus_stop_dict[item.NAME_] = bus_stop_value
            result.append(bus_stop_value)
            result.append("")
        routes_list = list(routes_set)
        routes_list.sort(key=natural_sort_key)
        result.append(f'Возможные маршруты: {" ".join(routes_list)}')
        return ArrivalInfo('\n'.join(result), "\n".join(headers), bus_stop_dict)

    @cachetools.func.ttl_cache(ttl=ttl_sec)
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
        def key_check(x: CdsRouteBus):
            return x.name_ and x.last_time_ and (now - x.last_time_) < hour

        cds_buses = self.load_all_cds_buses_from_db()
        if not cds_buses:
            return 'Ничего не нашлось'

        now = self.now()
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
    def load_codd_buses(self, bus_routes) -> Iterable[CoddRouteBus]:
        keys = set([x for x in self.codd_routes.keys() for r in bus_routes if x.upper() == r.upper()])
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

    @cachetools.func.ttl_cache()
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

    @cachetools.func.ttl_cache()
    def get_routes_on_bus_stop(self, bus_stop_name):
        result = []
        for (k, v) in self.bus_routes.items():
            if next((True for x in v if x.NAME_ == bus_stop_name), False):
                result.append(k)
        return result

    @cachetools.func.ttl_cache(maxsize=4096)
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
