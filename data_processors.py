import os
import random
from logging import Logger

import cachetools

from cds import CdsRequest
from data_types import UserLoc, ArrivalInfo
from helpers import parse_routes
from tracking import EventTracker

LOAD_TEST_DATA = False

try:
    import settings

    LOAD_TEST_DATA = settings.LOAD_TEST_DATA
except ImportError:
    LOAD_TEST_DATA = os.environ.get('LOAD_TEST_DATA', False)

ttl_sec = 10 if not LOAD_TEST_DATA else 0.0001


def isnamedtupleinstance(x):
    _type = type(x)
    bases = _type.__bases__
    if len(bases) != 1 or bases[0] != tuple:
        return False
    fields = getattr(_type, '_fields', None)
    if not isinstance(fields, tuple):
        return False
    return all(type(i) == str for i in fields)


def unpack_namedtuples(obj):
    if isinstance(obj, dict):
        return {key: unpack_namedtuples(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [unpack_namedtuples(value) for value in obj]
    elif isnamedtupleinstance(obj):
        return {key: unpack_namedtuples(value) for key, value in obj._asdict().items()}
    elif isinstance(obj, tuple):
        return tuple(unpack_namedtuples(value) for value in obj)
    else:
        return obj


def eliminate_numbers(d: dict, full_info, is_fraud) -> dict:
    if not full_info:
        d['name_'] = ''

    if is_fraud:
        d['last_lat_'] += random.uniform(-0.05, 0.05)
        d['last_lon_'] += random.uniform(-0.05, 0.05)
        d['obj_id_'] = random.uniform(0, 2000)
        d['proj_id_'] = random.uniform(0, 2000)
        raise Exception("Wrong request")

    return d


class BaseDataProcessor:
    def __init__(self, cds: CdsRequest, logger: Logger, tracker: EventTracker):
        self.cds = cds
        self.logger = logger
        self.tracker = tracker


class WebDataProcessor(BaseDataProcessor):
    def __init__(self, cds: CdsRequest, logger: Logger, tracker: EventTracker):
        super().__init__(cds, logger, tracker)

    @cachetools.func.ttl_cache(ttl=ttl_sec, maxsize=4096)
    def get_bus_info(self, query, lat, lon, full_info):
        user_loc = None
        if lat and lon:
            user_loc = UserLoc(float(lat), float(lon))
        routes_info = parse_routes(query)
        is_fraud = not full_info and len(routes_info.bus_routes) > 25

        result = self.cds.bus_request(routes_info, user_loc=user_loc, short_format=True)
        return {'q': query, 'text': result[0],
                'buses': [(eliminate_numbers(x[0]._asdict(), full_info, is_fraud),
                           x[1]._asdict() if x[1] and not is_fraud else {}) for x
                          in result[1]]}

    def get_arrival(self, query, lat, lon):
        matches = self.cds.matches_bus_stops(lat, lon)
        self.logger.info(f'{lat};{lon} {";".join([str(i) for i in matches])}')
        result_tuple = self.cds.next_bus_for_matches(tuple(matches), parse_routes(query))
        response = {'lat': lat, 'lon': lon, 'text': result_tuple[0], 'header': result_tuple[1],
                    'bus_stops': {v.bus_stop_name: v.text for v in result_tuple.arrival_details}}
        return response

    @cachetools.func.ttl_cache(ttl=ttl_sec)
    def get_arrival_by_name(self, query, station_query):
        result_tuple = self.cds.next_bus(station_query, parse_routes(query))
        if result_tuple.found:
            response = {'text': result_tuple[0], 'header': result_tuple[1],
                        'bus_stops': {v.bus_stop_name: v.text for v in
                                      result_tuple.arrival_details}}
        else:
            response = {'text': result_tuple[0], 'header': result_tuple[1],
                        'bus_stops': {k: '' for k in
                                      result_tuple.bus_stops}}
        return response

    def get_text_from_arrival_info(self, arrival_info: ArrivalInfo):
        def text_for_bus_stop(value):
            return f"({value.bus_stop_id}) {value.bus_stop_name}\n{value.text}"

        next_bus_text = '\n'.join([text_for_bus_stop(v) for v in arrival_info.arrival_details])
        return f'{arrival_info.header}\n{next_bus_text}'

    def get_arrival_by_id(self, query, busstop_id):
        bus_stop = self.cds.get_bus_stop_from_id(busstop_id)
        if bus_stop:
            search_params = parse_routes(query)
            arrival_info = self.cds.next_bus_for_matches((bus_stop,), search_params)
            result_text = self.get_text_from_arrival_info(arrival_info)
            response = {'result': result_text, 'arrival_info': unpack_namedtuples(arrival_info)}
            return response

    def get_bus_list(self):
        response = {'result': self.cds.codd_buses}
        return response

    @cachetools.func.ttl_cache(ttl=36000)
    def get_bus_stops(self):
        response = {'result': [x._asdict() for x in self.cds.all_bus_stops]}
        return response

    @cachetools.func.ttl_cache(ttl=36000)
    def get_bus_stops_for_routes(self):
        response = {'result': {route_name: [x._asdict() for x in bus_stops] for (route_name, bus_stops) in
                               self.cds.bus_routes.items()}}
        return response

    @cachetools.func.ttl_cache(ttl=15)
    def get_stats(self):
        user_stats = self.tracker.stats()
        bus_stats = self.cds.get_bus_statistics()
        return user_stats + '\n\n' + bus_stats.text


class TelegramDataProcessor(BaseDataProcessor):
    def __init__(self, cds: CdsRequest, logger: Logger):
        super().__init__(cds, logger)
