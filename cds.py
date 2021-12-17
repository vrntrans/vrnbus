import datetime
import os
import threading
import time
from collections import Counter, deque
from collections import defaultdict
from datetime import timedelta
from itertools import groupby, product
from logging import Logger
from typing import Iterable, Container, List, Optional, Deque, Union, Collection

import cachetools.func
import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from rtree import index

from data_types import ArrivalInfo, UserLoc, BusStop, LongBusRouteStop, CdsBusPosition, CdsRouteBus, \
    CdsBaseDataProvider, StatsData, ArrivalBusStopInfo, ArrivalBusStopInfoFull
from helpers import fuzzy_search_advanced, sort_routes
from helpers import get_time, natural_sort_key, SearchResult

LOAD_TEST_DATA = False

try:
    import settings

    LOAD_TEST_DATA = settings.LOAD_TEST_DATA
except ImportError:
    LOAD_TEST_DATA = os.environ.get('LOAD_TEST_DATA', False)

ttl_sec = 10 if not LOAD_TEST_DATA else 0.0001

tz = pytz.timezone('Europe/Moscow')

WATCHDOG_INTERVAL = 60


class CdsRequest:
    rtree_lock = threading.Lock()

    def __init__(self, logger: Logger, data_provider: CdsBaseDataProvider):
        self.logger = logger
        self.fake_header = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                                          '(KHTML, like Gecko) Chrome/63.0.3239.132 Safari/537.36'}
        self.data_provider = data_provider
        self.all_codd_routes = data_provider.load_codd_route_names()
        self.codd_routes = {k:v.ID_ for k,v in self.all_codd_routes.items()  if v.ROUTE_ACTIVE_}
        self.codd_buses = sort_routes(self.codd_routes)

        self.codd_new_routes = data_provider.load_new_codd_route_names()
        self.codd_new_buses = sort_routes(self.codd_new_routes.keys())

        self.bs_index: index.Index = None
        self.bs_routes_index = {}
        self.all_bus_stops = data_provider.load_bus_stops()
        self.bus_stops = [bs for bs in self.all_bus_stops if bs.LAT_ and bs.LON_]

        self.bus_stops_dict = {bs.ID: bs for bs in self.bus_stops}
        self.bus_stops_dict_name = {bs.NAME_: bs for bs in self.bus_stops}
        self.bus_routes = data_provider.load_bus_stations_routes()
        self.new_bus_routes = {}

        self.build_rtree_index(self.bus_stops)
        self.build_rtree_index_for_routes(self.bus_routes)

        self.all_cds_buses = []
        self.avg_speed = 18.0
        self.fetching_in_progress = False
        self.fetching_timestamp = datetime.datetime.now()
        self.last_bus_data = defaultdict(lambda: deque(maxlen=20))
        self.route_distances = {}
        self.bus_speed_dict = {}
        self.bus_last_speed_dict = {}
        self.bus_onroute_dict = {}
        self.speed_dict = {}
        self.speed_deque = deque(maxlen=10)
        self.wd_call_back = None

        self.bus_stats = []

        # self.update_all_cds_buses_from_db()
        self.scheduler = BackgroundScheduler()
        self.run_scheduled_task()

    def run_scheduled_task(self):
        self.scheduler.remove_all_jobs()
        self.scheduler.start()
        self.scheduler.add_job(self.update_all_cds_buses_from_db, 'interval', seconds=15, max_instances=1)
        self.scheduler.add_job(self.update_watch_dog, 'interval', seconds=WATCHDOG_INTERVAL)
        self.scheduler.add_job(self.load_new_routes_bg)

    def update_watch_dog(self):
        fetching_duration = (self.now() - self.fetching_timestamp).total_seconds()
        self.logger.debug(f'{fetching_duration=:.2f}')
        if self.fetching_in_progress and fetching_duration > WATCHDOG_INTERVAL:
            self.logger.error(f"SOMETHING GOES WRONG {fetching_duration=:.2f}")
            if self.wd_call_back:
                self.wd_call_back(f'Слишком долгое ожидание ответа от базы данных {fetching_duration:.0f} с, переподключение')

            self.scheduler.shutdown(wait=False)
            self.scheduler = BackgroundScheduler()

            self.run_scheduled_task()

    def load_new_routes_bg(self):
        self.new_bus_routes = self.data_provider.load_new_bus_stations_routes()

    def get_new_bus_routes(self):
        self.new_bus_routes = self.data_provider.load_new_bus_stations_routes()
        return self.new_bus_routes

    def stats_checking(self):
        self.logger.info("Hello")

    def get_last_bus_data(self, bus_name) -> Deque[CdsBusPosition]:
        return self.last_bus_data.get(bus_name)

    def add_last_bus_data(self, bus_name, bus_data: CdsBusPosition):
        value = self.last_bus_data[bus_name]
        if bus_data in value:
            return
        value.append(bus_data)

    def get_nearest(self, lat, lon) -> BusStop:
        if self.bs_index is None:
            self.build_rtree_index(self.bus_stops)
        ids = list(self.bs_index.nearest((lat, lon), 1))
        return self.bus_stops_dict.get(ids[0])

    def get_k_nearest(self, lat, lon, k=3) -> List[BusStop]:
        try:
            if self.bs_index is None:
                self.build_rtree_index(self.bus_stops)
            ids = self.bs_index.nearest((lat, lon), k)
            return [self.bus_stops_dict.get(i) for i in ids]
        except Exception:
            self.logger.exception(f'Error when process get_k_nearest({lat}, {lon}, {k})')
            self.build_rtree_index(self.bus_stops)

    def get_k_nearest_by_route(self, route_name, lat, lon, k=3) -> List[BusStop]:
        try:
            r_index = self.bs_routes_index.get(route_name)
            bus_stops = self.bus_routes.get(route_name, [])
            ids = [i for i in r_index.nearest((lat, lon), k)][:k]
            return [next(filter(lambda x: x.ID == i, bus_stops), None) for i in ids]
        except Exception:
            self.logger.exception(f'Error when process get_k_nearest({lat}, {lon}, {k})')

    def build_rtree_index(self, bus_stations: Iterable[BusStop]):
        try:
            self.logger.info("Recreate RTree index for bus stations")
            with self.rtree_lock:
                self.bs_index = index.Index()
                for bs in bus_stations:
                    self.bs_index.insert(bs.ID, (bs.LAT_, bs.LON_, bs.LAT_, bs.LON_))
            self.logger.info("Recreate RTree index for bus stations finished")
        except:
            self.bs_index = None
            self.logger.exception(f'Error when rebuild RTree index')

    def build_rtree_index_for_routes(self, bus_stations_for_routes):
        try:
            self.logger.info("Recreate RTree index for routes")
            with self.rtree_lock:
                for k, v in bus_stations_for_routes.items():
                    route_index = index.Index()
                    for bs in v:
                        route_index.insert(bs.ID, (bs.LAT_, bs.LON_, bs.LAT_, bs.LON_))
                    self.bs_routes_index[k] = route_index
            self.logger.info("Recreate RTree index for routes finished")
        except:
            self.bs_index = None
            self.logger.exception(f'Error when rebuild RTree index')

    @cachetools.func.ttl_cache()
    def matches_bus_stops(self, lat, lon, size=3):
        return self.get_k_nearest(lat, lon, size)

    @cachetools.func.ttl_cache(ttl=ttl_sec)
    def bus_request_as_list(self, bus_routes):
        def key_check(route: CdsRouteBus):
            return route.name_ and last_two_week < route.last_time_

        keys = set([x for x in self.all_codd_routes.keys() for r in bus_routes if x.upper() == r.upper()])

        bus_on_routes = self.load_cds_buses_from_db(tuple(keys))
        self.logger.debug(f'Loaded {len(bus_on_routes)} buses from DB for {bus_routes} query')
        if bus_on_routes:
            last_two_week = self.now() - timedelta(days=14)
            short_result = sorted([d for d in bus_on_routes if key_check(d)],
                                  key=lambda s: natural_sort_key(s.route_name_))
            return short_result
        return []

    def is_bus_on_the_route(self, route_name: str, bus_position: CdsBusPosition):
        if not bus_position.is_valid_coords():
            return False
        route_stops = self.bus_routes.get(route_name, [])

        if not route_stops or len(route_stops) < 2:
            return False

        result = self.get_k_nearest_by_route(route_name, bus_position.lat, bus_position.lon, 1)
        return bus_position.distance_km(result[0]) < 1

    def get_closest_bus_stop_checked(self, route_name: str, bus_positions: Container[CdsBusPosition]):
        bus_stops = self.bus_routes.get(route_name, [])

        if not bus_stops or len(bus_stops) < 2:
            self.logger.error(f"Empty bus_stops for {route_name}")
            return

        if not bus_positions:
            self.logger.error("Empty bus_positions for {route_name}")
            return

        last_position = bus_positions[-1]
        nearest_result = self.get_k_nearest_by_route(route_name, last_position.lat, last_position.lon, 2)

        (curr_1, curr_2) = nearest_result
        if curr_1.NUMBER_ == curr_2.NUMBER_ + 1:
            return curr_1
        elif curr_2.NUMBER_ == curr_1.NUMBER_ + 1:
            return curr_2

        m_num = bus_stops[len(bus_stops) // 2].NUMBER_
        curr_pos = {curr_1, curr_2}
        bus_positions = list(bus_positions)
        for prev_position in bus_positions[-1::-1]:
            closest_prev = self.get_k_nearest_by_route(route_name, prev_position.lat, prev_position.lon, 2)
            if set(closest_prev) == curr_pos:
                continue

            all_cases = product((curr_1, curr_2), closest_prev)
            for (s1, s2) in all_cases:
                n1, n2 = s1.NUMBER_, s2.NUMBER_
                if n1 > n2 and ((n1 <= m_num and n2 <= m_num) or (n1 >= m_num and n2 >= m_num)):
                    return s1

            self.logger.debug(f"Bus stop for {route_name} ({last_position.lat}, {last_position.lon})")

        return curr_1

    @cachetools.func.ttl_cache(maxsize=4096)
    def get_closest_bus_stop(self, bus_info: CdsRouteBus):
        if not bus_info.is_valid_coords():
            return
        threshold = 0.5
        bus_stop = self.bus_stops_dict_name.get(bus_info.bus_station_)
        if bus_stop and bus_info.distance_km(bus_stop) < threshold:
            return bus_stop
        elif self.now() - bus_info.last_time_ > timedelta(minutes=15):
            return self.get_nearest(bus_info.last_lat_, bus_info.last_lon_)

        bus_positions = self.last_bus_data[bus_info.name_]
        if not bus_positions:
            bus_positions.append(bus_info.get_bus_position())
        closest_on_route = self.get_closest_bus_stop_checked(bus_info.route_name_, bus_positions)

        if closest_on_route and bus_info.distance(closest_on_route) < threshold:
            return closest_on_route

        closest_stop = self.get_nearest(bus_info.last_lat_, bus_info.last_lon_)
        if closest_stop and bus_info.distance(closest_stop) < threshold:
            return closest_stop

        result = min((bus_stop, closest_on_route, closest_stop), key=bus_info.distance)

        if not bus_info.bus_station_:
            self.logger.debug(f"Empty station: {bus_info.short()} {result}")

        return result

    @cachetools.func.ttl_cache(maxsize=4096)
    def bus_station(self, bus_info: CdsRouteBus):
        if not bus_info.is_valid_coords():
            self.logger.debug(f"Not valid coords {bus_info}")
            return
        result = self.get_closest_bus_stop(bus_info)
        if not result or not result.NAME_:
            self.logger.debug(f"{result} {bus_info}")
        return result

    def station(self, d: CdsRouteBus, user_loc: UserLoc = None, full_info=False, show_route_name=True):
        bus_station = self.bus_station(d)
        dist = f'{(d.distance_km(bus_stop=bus_station)):.1f} км'
        route_name = f"{d.route_name_} " if show_route_name else ""
        day_info = ""
        if self.now() - d.last_time_ > timedelta(days=1):
            day_info = f'{d.last_time_:%d.%m} '
        speed_info = f' {d.last_speed_:.1f} ~ {self.bus_speed_dict.get(d.name_, 18):.1f} км/ч'
        result = f"{route_name}{day_info}{get_time(d.last_time_):%H:%M} {bus_station and bus_station.NAME_} {dist}"

        if full_info:
            orig_bus_stop = ""
            if not bus_station == d.bus_station_:
                orig_bus_stop = (' | ' + str(d.bus_station_))

            return f"{result} {'ВЫВЕДЕН ' if d.obj_output else ''}{d.name_},{speed_info} {orig_bus_stop}"
        return result + speed_info

    def bus_active(self, d: CdsRouteBus, full_info):
        if full_info:
            return True
        if d.obj_output:
            return
        if not self.bus_onroute_dict.get(d.name_, False):
            return
        if self.bus_speed_dict.get(d.name_, 18) < 1:
            return
        now = self.now()
        delta = timedelta(minutes=15)
        return d.last_time_ and (now - d.last_time_) < delta

    def filter_bus_list(self, bus_list, search_result: SearchResult):

        def filtered(d: CdsRouteBus):
            return d.filter_by_name(search_result.bus_filter)

        stations_filtered = [(d, self.get_next_bus_stop(d.route_name_, self.bus_station(d)))
                             for d in bus_list if filtered(d) and self.bus_active(d, search_result.full_info)]
        return stations_filtered

    @cachetools.func.ttl_cache(ttl=ttl_sec)
    def bus_request(self, search_result: SearchResult, user_loc: UserLoc = None, short_format=False):
        if search_result.all_buses:
            keys = set(self.all_codd_routes.keys())
        else:
            keys = set([x for x in self.all_codd_routes.keys()
                        for r in search_result.bus_routes if x.upper() == r.upper()])

        if not keys and not search_result.bus_filter:
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

    def load_all_cds_buses_from_db(self) -> List[CdsRouteBus]:
        return self.all_cds_buses

    def update_all_cds_buses_from_db(self):
        def calc_speed(bus_positions: Iterable[CdsBusPosition]):
            curr_pos = bus_positions[0]
            dist = 0
            for pos in bus_positions:
                if not pos.is_valid_coords():
                    continue
                dist = dist + pos.distance_km(position=curr_pos)
                curr_pos = pos
            delta = bus_positions[-1].last_time - bus_positions[0].last_time
            if delta.seconds == 0:
                return 0.00001
            return dist * 3600 / delta.seconds

        def calc_result_speed(bus_positions: List[CdsBusPosition]):
            if len(bus_positions) < 2:
                return 18
            last_speed = calc_speed(bus_positions[:3])
            avg_speed = calc_speed(bus_positions)

        def update_average_speeds():
            for (k, bus_positions) in self.last_bus_data.items():
                if len(bus_positions) < 2:
                    continue
                bus_positions = list(filter(lambda bus: bus.is_valid_coords(), bus_positions))
                if not bus_positions:
                    continue

                bus_positions = list(sorted(bus_positions, key=lambda x: x.last_time))

                last_speed = calc_speed(bus_positions[-3:])
                avg_speed = calc_speed(bus_positions)
                if avg_speed < 5 < last_speed:
                    self.last_bus_data[k] = deque(bus_positions[-3:], maxlen=20)
                    avg_speed = last_speed
                elif last_speed > avg_speed * 2:
                    self.last_bus_data[k] = deque(bus_positions[-10:], maxlen=20)
                    avg_speed = last_speed = calc_speed(self.last_bus_data[k])

                self.bus_last_speed_dict[k] = last_speed
                self.bus_speed_dict[k] = avg_speed

        def update_last_bus_data(buses: List[CdsRouteBus]):
            for bus in buses:
                bus_position = bus.get_bus_position()
                self.add_last_bus_data(bus.name_, bus_position)
                self.bus_onroute_dict[bus.name_] = self.is_bus_on_the_route(bus.route_name_, bus_position)
            update_average_speeds()
            return [x._replace(avg_speed=self.bus_speed_dict.get(x.name_, 18),
                               avg_last_speed=self.bus_last_speed_dict.get(x.name_, 18)) for x in buses]

        while self.fetching_in_progress:
            self.logger.info("Waiting for previous DB query")
            time.sleep(5)
        try:
            self.fetching_in_progress = True
            self.fetching_timestamp = datetime.datetime.now()
            all_buses = self.data_provider.load_all_cds_buses()
            result = update_last_bus_data(all_buses)
            self.bus_stats.append((self.now(), sum((self.bus_active(bus, False) == True for bus in result ))))
            result.sort(key=lambda s: s.last_time_, reverse=True)

        finally:
            self.fetching_in_progress = False
        self.all_cds_buses = result

    @cachetools.func.ttl_cache(ttl=ttl_sec)
    def calc_avg_speed(self):
        def time_filter(bus: CdsRouteBus):
            if not bus.last_station_time_ or not bus.last_time_:
                return False
            if bus.last_time_ < last_n_minutes:
                return False
            if bus.last_station_time_ < last_n_minutes:
                return False
            return True

        bus_full_list = self.load_all_cds_buses_from_db()
        now = self.now()
        last_n_minutes = now - timedelta(minutes=15)
        bus_list = list(filter(time_filter, bus_full_list))
        self.logger.debug(f'Buses in last 15 munutes {len(bus_list)} from {len(bus_full_list)}')
        sum_speed = sum((x.last_speed_ for x in bus_list))
        if len(bus_list) > 0:
            self.speed_deque.append(sum_speed * 1.0 / len(bus_list))
            self.avg_speed = sum(self.speed_deque) / len(self.speed_deque)
        self.logger.info(f'Average speed for all buses: {self.avg_speed:.1f}')
        speed_dict = {}
        curr_bus_routes = Counter((x.route_name_ for x in bus_list))
        for (route, size) in curr_bus_routes.items():
            speed_dict[route] = sum((
                self.bus_speed_dict.get(x.name_, 18) for x in bus_list
                if x.route_name_ == route and self.bus_speed_dict.get(x.name_, 18) > 1)) / size
        self.speed_dict = speed_dict

    @cachetools.func.ttl_cache(ttl=ttl_sec)
    def load_cds_buses_from_db(self, keys) -> Collection[CdsRouteBus]:
        all_buses = self.load_all_cds_buses_from_db()
        if not keys:
            return all_buses
        result = [x for x in all_buses if x.route_name_ in keys]
        return result

    def get_bus_stop_id(self, name):
        bus_stop = self.bus_stops_dict_name.get(name)
        if not bus_stop:
            return -1
        return bus_stop.ID or self.bus_stops.index(bus_stop)

    def get_bus_stop_from_id(self, id) -> Union[BusStop, None]:
        bus_stop = self.bus_stops_dict.get(id)
        if bus_stop:
            return bus_stop
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
            return ArrivalInfo(f'Уточните остановку. Найденные варианты:\n{first_matches}',
                               'Уточните остановку. Найденные варианты:',
                               bus_stops=bus_stop_matches[:20])
        return self.next_bus_for_matches(tuple(bus_stop_matches), search_result)

    @cachetools.func.ttl_cache(ttl=ttl_sec, maxsize=4096)
    def get_bus_distance_to(self, bus_route_names, bus_stop_name, bus_filter) -> List[ArrivalBusStopInfo]:
        def time_filter(bus_info: CdsRouteBus):
            if not bus_info.last_time_ or bus_info.last_time_ < last_n_minutes:
                return False
            if bus_info.last_station_time_ and bus_info.last_station_time_ < last_n_minutes:
                return False
            return True

        def time_to_arrive(km, last_time, avg_speed):
            speed = avg_speed if avg_speed > 0.1 else 0.1
            speed = speed if speed > 100 else 18.0
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
            if not bus.filter_by_name(bus_filter):
                continue
            closest_stop = self.get_closest_bus_stop(bus)
            if not closest_stop:
                continue
            bus_dist = bus.distance_km(closest_stop)
            same_station = bus.bus_station_ == bus_stop_name
            route_dist = self.get_dist(bus.route_name_, closest_stop.NAME_, bus_stop_name)
            if route_dist == 0 and not same_station:
                continue
            if bus.bus_station_ != closest_stop.NAME_:
                route_dist += self.get_dist(bus.route_name_, bus.bus_station_, bus_stop_name)
            dist = bus_dist + route_dist
            time_left = time_to_arrive(dist, bus.last_time_, self.bus_speed_dict.get(bus.name_, 18))
            if (same_station or route_dist > 0) and dist < 20 and time_left < 30:
                result.append(ArrivalBusStopInfo(bus, dist, time_left))
        return result

    # @cachetools.func.ttl_cache(ttl=30)
    def next_bus_for_matches(self, bus_stop_matches, search_result: SearchResult) -> ArrivalInfo:
        def bus_info(bus: CdsRouteBus, distance, time_left):
            arrival_time = f"{time_left:>2.0f} мин" if time_left >= 1 else "ждём"
            info = f'{bus.route_name_:>5} {arrival_time}'
            if search_result.full_info:
                info += f' {distance:.2f} км {bus.last_time_:%H:%M} {bus.name_} {self.bus_station(bus).NAME_}'
            return info

        result = [f'Время: {self.now():%H:%M:%S}']
        routes_set = set()
        routes_filter = list(set([x for x in self.codd_routes.keys()
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

        arrival_details = []

        headers = result[:]
        for item in bus_stop_matches:
            arrival_routes = self.get_routes_on_bus_stop(item.ID)
            arrival_routes = [x for x in arrival_routes if not routes_filter or x in routes_filter]
            if not arrival_routes:
                continue
            if routes_filter:
                avg_speed_routes = sum((self.speed_dict.get(x, self.avg_speed)
                                        for x in routes_filter)) / len(routes_filter)
                self.logger.info(f'Average speed on routes {arrival_routes} {avg_speed_routes:.2f} kmh')

            routes_set.update(arrival_routes)
            arrival_routes = tuple(sorted(arrival_routes, key=natural_sort_key))
            result.append(f'{item.NAME_}:')
            arrival_buses = self.get_bus_distance_to(arrival_routes, item.NAME_, search_result.bus_filter)
            arrival_buses.sort(key=lambda x: x[2])
            bus_stop_value = '\n'.join((bus_info(*d) for d in arrival_buses))
            arrival_details.append(
                ArrivalBusStopInfoFull(item.ID, item.NAME_, item.LAT_, item.LON_, item.AZMTH, bus_stop_value, list(arrival_routes),
                                       arrival_buses))

            result.append(bus_stop_value)
            result.append("")
        routes_list = list(routes_set)
        routes_list.sort(key=natural_sort_key)
        result.append(f'Возможные маршруты: {" ".join(routes_list)}')
        return ArrivalInfo('\n'.join(result), "\n".join(headers), arrival_details, found=True)

    @cachetools.func.ttl_cache(ttl=ttl_sec)
    def get_bus_statistics(self, full_info=False) -> Optional[StatsData]:
        def time_check(bus: CdsRouteBus, last_time):
            if not bus.last_time_ or bus.last_time_ < last_time:
                return False
            # if bus.last_station_time_ and bus.last_station_time_ < last_time:
            #     return False
            return True

        def count_buses(buses: Iterable[CdsRouteBus], time_interval):
            return sum(1 for i in buses if time_check(i, now - time_interval) and i.obj_output != 1)

        cds_buses = self.load_all_cds_buses_from_db()
        if not cds_buses:
            return

        now = self.now()
        hour_1 = count_buses(cds_buses, timedelta(hours=1))
        minutes_1 = count_buses(cds_buses, timedelta(minutes=1))
        minutes_10 = count_buses(cds_buses, timedelta(minutes=10))
        minutes_30 = count_buses(cds_buses, timedelta(minutes=30))
        total = count_buses(cds_buses, timedelta(days=7))
        bus_stats_text = f"1 ч. 30 мин. 10 мин.\n{hour_1:<5} {minutes_30:^5} {minutes_10:5}\nЗа минуту: {minutes_1}\nВсего: {total}"
        self.logger.info(f"{hour_1: <5} {minutes_30:5} {minutes_10:5}")
        if hour_1 > 0:
            buses_list = [f'Время: {self.now():%H:%M:%S}']
            if full_info:
                short_result = [d for d in cds_buses if time_check(d, now - timedelta(minutes=10))]
                sort_routes = sorted(short_result, key=lambda x: natural_sort_key(x.route_name_))
                grouped = [(k, len(list(g))) for k, g in
                           groupby(sort_routes, lambda x: f'{x.route_name_:5s} ({x.proj_id_:3d})')]
                buses_list += (('{:10s} => {}'.format(i[0], i[1])) for i in grouped)
            buses_list.append(bus_stats_text)
            text = '\n'.join(buses_list)
            text += f'\nНа линии: {self.bus_stats[-1][1]}'
            return StatsData(minutes_1, minutes_10, minutes_30, hour_1, len(cds_buses), text)

    def get_dist_bus_stop(self, src: LongBusRouteStop, dst: LongBusRouteStop):
        key = (src.ID, dst.ID)
        if key in self.route_distances:
            return self.route_distances.get(key)
        value = src.distance_km(dst)
        self.route_distances[key] = value
        return value

    def get_dist(self, route_name, bus_stop_start, bus_stop_stop):
        route: Iterable[LongBusRouteStop] = self.bus_routes.get(route_name, [])

        dist = 0
        prev_stop = None
        for bus_stop in route:
            if prev_stop:
                dist += self.get_dist_bus_stop(prev_stop, bus_stop)
                prev_stop = bus_stop
            if not prev_stop and bus_stop.NAME_ == bus_stop_start:
                prev_stop = bus_stop
            if bus_stop.NAME_ == bus_stop_stop:
                break
        return dist

    @cachetools.func.ttl_cache(maxsize=4096)
    def get_routes_on_bus_stop(self, bus_stop_id):
        result = []
        for (k, v) in self.bus_routes.items():
            if next((True for x in v if x.ID == bus_stop_id), False):
                result.append(k)
        return result

    @cachetools.func.ttl_cache(maxsize=4096)
    def get_next_bus_stop(self, route_name, bus_stop: LongBusRouteStop):
        bus_stop_name = bus_stop and bus_stop.NAME_
        route = self.bus_routes.get(route_name, [])
        if not route:
            self.logger.debug(f"Wrong params {route_name}, {bus_stop_name}. Didn't find anything")
            return bus_stop
        size = len(route)
        for (i, v) in enumerate(route):
            if v.NAME_ == bus_stop_name:
                if (i + 2) < size:
                    return route[i + 1]
                if i + 1 == size:
                    return v
                return v
        self.logger.debug(f"Wrong params {route_name}, {bus_stop_name}")
        bus_stop = self.bus_stops_dict_name.get(bus_stop_name)
        if bus_stop:
            return bus_stop
        else:
            self.logger.debug(f"Cannot found {bus_stop_name}, will return first bus_stop")
            return self.bus_stops[0]

    def is_bus_stop_name(self, s):
        if not s or not isinstance(s, str):
            return False
        if s in self.codd_routes:
            return False
        return any((x for x in self.bus_stops if fuzzy_search_advanced(s, x.NAME_)))
