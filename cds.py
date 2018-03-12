import heapq
import json
import time
from collections import Counter, deque
from collections import defaultdict
from datetime import timedelta
from itertools import groupby, product
from logging import Logger
from pathlib import Path
from typing import Iterable, Dict, Container

import cachetools.func
import pytz

from data_types import ArrivalInfo, UserLoc, BusStop, LongBusRouteStop, CdsBusPosition, CdsRouteBus, CdsBaseDataProvider
from helpers import fuzzy_search_advanced
from helpers import get_time, natural_sort_key, distance, retry_multi, SearchResult

LOAD_TEST_DATA = False

try:
    import settings
    LOAD_TEST_DATA = settings.LOAD_TEST_DATA
except ImportError:
    pass

ttl_sec = 30 if not LOAD_TEST_DATA else 0.001
ttl_db_sec = 60 if not LOAD_TEST_DATA else 0.001

tz = pytz.timezone('Europe/Moscow')


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
    def __init__(self, logger: Logger, data_provider: CdsBaseDataProvider):
        self.logger = logger
        self.fake_header = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                                          '(KHTML, like Gecko) Chrome/63.0.3239.132 Safari/537.36'}
        self.bus_stops = [BusStop(**i) for i in init_bus_stops()]
        self.bus_routes = init_bus_routes()
        self.data_provider = data_provider

        self.cds_routes = self.init_cds_routes()
        self.codd_routes = self.init_codd_routes()
        self.avg_speed = 18.0
        self.fetching_in_progress = False
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

    def init_codd_routes(self) -> Dict:
        my_file = Path("bus_routes_codd.json")
        with open(my_file, 'rb') as f:
            return json.load(f)

    @staticmethod
    def init_cds_routes():
        my_file = Path("bus_routes_cds.json")
        with open(my_file, 'rb') as f:
            return json.load(f)

    @cachetools.func.ttl_cache()
    def matches_bus_stops(self, lat, lon, size=3):
        def distance_key(item):
            return distance(item.LAT_, item.LON_, lat, lon)

        return sorted(self.bus_stops, key=distance_key)[:size]

    @cachetools.func.ttl_cache(ttl=ttl_sec)
    def bus_request_as_list(self, bus_routes):
        def key_check(route: CdsRouteBus):
            return route.name_ and last_week < route.last_time_

        keys = set([x for x in self.cds_routes.keys() for r in bus_routes if x.upper() == r.upper()])

        routes = self.load_cds_buses_from_db(tuple(keys))
        self.logger.debug(routes)
        if routes:
            last_week = self.now() - timedelta(days=7)
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

            self.logger.warning(f"{last_position}")

        return curr_1

    @cachetools.func.ttl_cache(ttl=ttl_sec, maxsize=2048)
    def get_closest_bus_stop(self, bus_info: CdsRouteBus):
        threshold = 0.005
        bus_stop = next((x for x in self.bus_stops
                         if bus_info.bus_station_ and x.NAME_ == bus_info.bus_station_), None)
        if bus_stop and bus_info.distance(bus_stop) < threshold:
            return bus_stop

        bus_positions = self.last_bus_data[bus_info.name_]
        if not bus_positions:
            bus_positions.append(bus_info.get_bus_position())
        closest_on_route = self.get_closest_bus_stop_checked(bus_info.route_name_, bus_positions)


        if closest_on_route and bus_info.distance(closest_on_route) < threshold:
            return closest_on_route

        closest_stop = min(self.bus_stops, key=bus_info.distance)
        if closest_stop and bus_info.distance(closest_stop) < threshold:
            return closest_stop

        result = min((bus_stop, closest_on_route, closest_stop), key=bus_info.distance)

        if not bus_info.bus_station_:
            self.logger.debug(f"Empty station: {bus_info.short()} {result}")

        return result

    @cachetools.func.ttl_cache(ttl=ttl_sec)
    def bus_station(self, bus_info: CdsRouteBus):
        result = self.get_closest_bus_stop(bus_info)
        if not result.NAME_:
            self.logger.error(f"{result} {bus_info}")
        return result.NAME_

    def station(self, d: CdsRouteBus, user_loc: UserLoc = None, full_info=False, show_route_name=True):
        bus_station = self.bus_station(d)
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
        stations_filtered = [(d, self.get_next_bus_stop(d.route_name_, self.bus_station(d)))
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

    def now(self):
        return self.data_provider.now()

    @cachetools.func.ttl_cache(ttl=ttl_db_sec)
    def load_all_cds_buses_from_db(self) -> Iterable[CdsRouteBus]:
        def update_last_bus_data(buses):
            for bus in buses:
                self.add_last_bus_data(bus.name_, bus.get_bus_position())
        while self.fetching_in_progress:
            self.logger.info("Waiting for previous DB query")
            time.sleep(1)
        try:
            self.fetching_in_progress = True
            result = self.data_provider.load_all_cds_buses()
            update_last_bus_data(result)
            result.sort(key=lambda s: s.last_time_, reverse=True)
        finally:
            self.fetching_in_progress = False
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

    def get_bus_stop_id(self, name):
        bus_stop = next(filter(lambda x: x.NAME_ == name, self.bus_stops), None)
        if not bus_stop:
            return -1
        return self.bus_stops.index(bus_stop)

    def get_bus_stop_from_id(self, id) -> BusStop:
        if id < 0 or id >= len(self.bus_stops):
            return None
        return self.bus_stops[id]

    @cachetools.func.ttl_cache(ttl=ttl_sec)
    def next_bus(self, bus_stop_query, search_result) -> ArrivalInfo:
        bus_stop_matches = [x for x in self.bus_stops if fuzzy_search_advanced(bus_stop_query, x.NAME_)]
        if not bus_stop_matches:
            text = f'Остановки c именем "{bus_stop_query}" не найдены'
            return ArrivalInfo(text=text, header=text)
        if len(bus_stop_matches) > 5:
            first_matches = '\n'.join([x.NAME_ for x in bus_stop_matches[:20]])
            bus_stop_dict = {x.NAME_: '' for x in bus_stop_matches[:20]}
            return ArrivalInfo(f'Уточните остановку. Найденные варианты:\n{first_matches}',
                               'Уточните остановку. Найденные варианты:', bus_stop_dict)
        return self.next_bus_for_matches(tuple(bus_stop_matches), search_result)

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
            closest_stop = self.get_closest_bus_stop(bus)
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
    def next_bus_for_matches(self, bus_stop_matches, search_result: SearchResult) -> ArrivalInfo:
        def bus_info(bus: CdsRouteBus, distance, time_left):
            arrival_time = f"{time_left:>2.0f} мин" if time_left >= 1 else "ждём"
            info = f'{bus.route_name_:>5} {arrival_time}'
            if search_result.full_info:
                info += f' {distance:.2f} км {bus.last_time_:%H:%M} {bus.name_} {self.bus_station(bus)}'
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
            arrival_buses = tuple(sorted(arrival_buses, key=natural_sort_key))
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

    @cachetools.func.ttl_cache()
    def get_all_buses(self):
        def time_check(bus: CdsRouteBus, last_time):
            if not bus.last_time_ or bus.last_time_ < last_time:
                return False
            return True

        def count_buses(buses: Iterable[CdsRouteBus], time_interval):
            return sum(1 for i in buses if time_check(i, now - time_interval))

        cds_buses = self.load_all_cds_buses_from_db()
        if not cds_buses:
            return 'Ничего не нашлось'

        now = self.now()
        short_result = [d for d in cds_buses if time_check(d, now - timedelta(hours=1))]
        last_hour = len(short_result)
        short_result = sorted(short_result, key=lambda x: natural_sort_key(x.route_name_))
        grouped = [(k, len(list(g))) for k, g in groupby(short_result, lambda x: f'{x.route_name_:5s} ({x.proj_id_:3d})')]
        minutes_10 = count_buses(short_result, timedelta(minutes=10))
        minutes_30 = count_buses(short_result, timedelta(minutes=30))
        bus_stats_text = f"1 h. {last_hour} / 30 min. {minutes_30} / 10 min. {minutes_10} from {len(cds_buses)}"
        self.logger.info(bus_stats_text)
        if short_result:
            buses = ' \n'.join((('{:10s} => {}'.format(i[0], i[1])) for i in grouped))
            buses += '\n' + bus_stats_text
            return buses

        return 'Ничего не нашлось'

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
        self.logger.debug(f"Wrong params {route_name}, {bus_stop_name}")
        bus_stop = next((x for x in self.bus_stops if x.NAME_ == bus_stop_name), None)
        if bus_stop:
            return bus_stop
        else:
            self.logger.error(f"Cannot found {bus_stop_name}, will return first bus_stop")
            return self.bus_stops[0]
