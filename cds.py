import codecs
import json
from datetime import datetime, timedelta
from itertools import groupby
from pathlib import Path

import cachetools.func
import requests

from helpers import get_time, natural_sort_key

cds_url_base = 'http://195.98.79.37:8080/CdsWebMaps/'
codd_base_usl = 'http://195.98.83.236:8080/CitizenCoddWebMaps/'
ttl_sec = 60


class CdsRequest():
    def __init__(self, logger):
        self.cookies = {'JSESSIONID': 'C8ED75C7EC5371CBE836BDC748BB298F', 'session_id': 'vrntrans'}
        self.bus_stops = self.init_bus_stops()
        self.routes_base = self.init_routes()
        self.logger = logger
        self.fake_header = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
                  'Chrome/63.0.3239.132 Safari/537.36'}

    def load_bus_routes(self) -> {}:
        routes_base_local = {}
        r = requests.get(f'{cds_url_base}GetBuses', cookies=self.cookies, headers=self.fake_header)
        if r.text:
            result = json.loads(r.text)
            for v in result:
                if 'proj_id_' in v and 'route_name_' in v:
                    route = v['route_name_']
                    if route not in routes_base_local:
                        routes_base_local[v['route_name_']] = v['proj_id_']
        with open('bus_routes.json', 'wb') as f:
            json.dump(routes_base_local, codecs.getwriter('utf-8')(f), ensure_ascii=False, indent=4)
        return routes_base_local

    def init_routes(self):
        my_file = Path("bus_routes.json")
        if my_file.is_file():
            with open(my_file, 'rb') as f:
                return json.load(f)
        else:
            return self.load_bus_routes()


    def init_bus_stops(self):
        with open('bus_stops.json', 'rb') as f:
            return json.load(f)

    @cachetools.func.ttl_cache()
    def matches_bus_stops(self, lat, lon, size=3):
        distance = lambda item: pow(pow(item['LON_'] - lat, 2) + pow(item['LAT_'] - lon, 2), 0.5)
        return sorted(self.bus_stops, key=distance)[:size]

    @cachetools.func.ttl_cache(ttl=60)
    def bus_request(self, full_info=False, bus_route=tuple(), filter='' ):
        def filtered(d):
            return filter=='' or filter in d['name_']
        def station(d):
            if full_info:
               return f"{d['route_name_']} {get_time(d['last_time_']):%H:%M} {d.get('bus_station_')} {d['name_']} "
            else:
                return f"{d['route_name_']}, {get_time(d['last_time_']):%H:%M}, {d.get('bus_station_')}"

        if not bus_route:
            return 'Не заданы маршруты'
        short_result = self.bus_request_as_list(bus_route)
        if short_result:
            stations = [station(d) for d in short_result if filtered(d)]
            if stations:
                return ' \n'.join(stations)

        return 'Ничего не нашлось'

    @cachetools.func.ttl_cache(ttl=60)
    def bus_request_pro(self, bus_route):
        print('bus_route', bus_route)
        if not bus_route:
            return 'Не заданы маршруты'
        short_result = self.bus_request_as_list(bus_route)

        if short_result:
            print(short_result)
            stations = ' \n'.join(
                f"{d['route_name_']} {get_time(d['last_time_']):%H:%M} {d.get('bus_station_')} {d['name_']} " for d in
                short_result)
            print(stations)
            return stations

        return 'Ничего не нашлось'

    @cachetools.func.ttl_cache(ttl=90)
    def next_bus_for_lat_lon(self, lat, lon):
        url = f'{codd_base_usl}GetNextBus'
        payload = {'lat': lat, 'lon': lon}
        r = requests.post(url, data=payload, headers=self.fake_header)
        self.logger.info(f"{r.url} {payload} {r.elapsed}")
        if r.text:
            result = json.loads(r.text)
            return result


    @cachetools.func.ttl_cache(ttl=ttl_sec)
    def load_all_routes(self, keys):
        routes = [{'proj_ID': self.routes_base.get(k), 'route': k} for k in keys]
        if not routes:
            return []
        payload = {'routes': json.dumps(routes)}
        self.logger.info(f"bus_request_as_list {routes}")
        url = f'{cds_url_base}GetRouteBuses'
        r = requests.post(url, cookies=self.cookies, data=payload, headers=self.fake_header)
        self.logger.info(f"{r.url} {payload} {r.elapsed}")
        self.logger.debug(f"{r.text}")

        if r.text:
            return json.loads(r.text)
        return []

    @cachetools.func.ttl_cache(ttl=ttl_sec)
    def bus_request_as_list(self, bus_route):
        url = f'{cds_url_base}GetRouteBuses'
        if not bus_route:
            return []
        keys = set([x for x in self.routes_base.keys() for r in bus_route if x.upper() == r.upper()])

        routes = self.load_all_routes(tuple(keys))
        if routes:
            now = datetime.now()
            hour = timedelta(hours=1)
            key_check = lambda x: 'name_' in x and 'last_time_' in x and (now - get_time(x['last_time_'])) < hour
            short_result = sorted([d for d in routes if key_check(d)], key=lambda s: natural_sort_key(s['route_name_']))
            return short_result
        return []

    @cachetools.func.ttl_cache(ttl=90)
    def next_bus(self, bus_stop, user_bus_list):
        bus_stop = ' '.join(bus_stop)
        bus_stop_matches = [x for x in self.bus_stops if bus_stop.upper() in x['NAME_'].upper()]
        print(bus_stop, bus_stop_matches)
        if not bus_stop_matches:
            return f'Остановки c именем "{bus_stop}" не найдены'
        if len(bus_stop_matches) > 5:
            first_matches = '\n'.join([x['NAME_'] for x in bus_stop_matches[:20]])
            return f'Уточните остановку. Найденные варианты:\n{first_matches}'
        return self.next_bus_for_matches(bus_stop_matches, user_bus_list)


    # @cachetools.func.ttl_cache(ttl=60)
    def next_bus_for_matches(self, bus_stop_matches, user_bus_list):
        result = []
        if user_bus_list:
            result.append(f"Фильтр по маршрутам: {' '.join(user_bus_list)}. Настройка: /settings")
        for item in bus_stop_matches:
            arrivals = self.next_bus_for_lat_lon(item['LAT_'], item['LON_'])
            if arrivals:
                header = arrivals[0]
                items = [x for x in arrivals[1:] if x['time_'] > 0 and (not user_bus_list or x["rname_"].strip() in user_bus_list)]
                items.sort(key=lambda s: natural_sort_key(s['rname_']))
                if not items:
                    result.append(f'Остановка {header["rname_"]}: нет данных')
                    continue
                next_bus_info = f"Остановка {header['rname_']}:\n"
                next_bus_info += '\n'.join((f"{x['rname_']} - {x['time_']} мин" for x in items))
                result.append(next_bus_info)
        return '\n'.join(result)

    @cachetools.func.ttl_cache()
    def get_all_buses(self):
        def key_check(x):
            return 'name_' in x and 'last_time_' in x and (now - get_time(x['last_time_'])) < hour

        r = requests.get(f'{cds_url_base}GetBuses', cookies=self.cookies, headers=self.fake_header)
        self.logger.info(f"{r.url} {r.elapsed}")
        if r.text:
            result = json.loads(r.text)
            now = datetime.now()
            hour = timedelta(hours=1)
            short_result = [(d['name_'], d['last_time_'], d['route_name_'], d['proj_id_']) for d in result if
                            key_check(d)]
            short_result = sorted(short_result, key=lambda x: natural_sort_key(x[2]))
            grouped = [(k, len(list(g))) for k, g in groupby(short_result, lambda x: f'{x[2]} ({x[3]})')]
            if short_result:
                buses = ' \n'.join((('{} => {}'.format(i[0], i[1])) for i in grouped))
                return buses

        return 'Ничего не нашлось'