from logging import Logger

from cds import CdsRequest
from data_types import UserLoc, ArrivalInfo
from helpers import parse_routes, natural_sort_key


class BaseDataProcessor:
    def __init__(self, cds: CdsRequest, logger: Logger):
        self.cds = cds
        self.logger = logger


class WebDataProcessor(BaseDataProcessor):
    def __init__(self, cds: CdsRequest, logger: Logger):
        super().__init__(cds, logger)

    def get_bus_info(self, query, lat, lon, full_info):
        def eliminate_numbers(d: dict) -> dict:
            if not full_info:
                d['name_'] = ''
            return d

        user_loc = None
        if lat and lon:
            user_loc = UserLoc(float(lat), float(lon))
        result = self.cds.bus_request(parse_routes(query), user_loc=user_loc, short_format=True)
        return {'q': query, 'text': result[0],
                'buses': [(eliminate_numbers(x[0]._asdict()), x[1]._asdict() if x[1] else {}) for x in result[1]]}

    def get_arrival(self, query, lat, lon):
        matches = self.cds.matches_bus_stops(lat, lon)
        self.logger.info(f'{lat};{lon} {";".join([str(i) for i in matches])}')
        result = self.cds.next_bus_for_matches(tuple(matches), parse_routes(query))
        response = {'lat': lat, 'lon': lon, 'text': result[0], 'header': result[1], 'bus_stops': result[2]}
        return response

    def get_arrival_by_name(self, query, station_query):
        result_tuple = self.cds.next_bus(station_query, parse_routes(query))
        response = {'text': result_tuple[0], 'header': result_tuple[1], 'bus_stops': result_tuple[2]}
        return response

    def get_text_from_arrival_info(self, arrival_info: ArrivalInfo):
        def text_for_bus_stop(key, value):
            return f"({self.cds.get_bus_stop_id(key)}) {key}\n{value}"

        next_bus_text = '\n'.join([text_for_bus_stop(k, v) for (k, v) in arrival_info.bus_stops.items()])
        return f'{arrival_info.header}\n{next_bus_text}'

    def get_arrival_by_id(self, query, busstop_id):
        bus_stop = self.cds.get_bus_stop_from_id(busstop_id)
        if bus_stop:
            search_params = parse_routes(query)
            arrival_info = self.cds.next_bus_for_matches((bus_stop,), search_params)
            result_text = self.get_text_from_arrival_info(arrival_info)
            response = {'result': result_text, 'arrival_info': arrival_info}
            return response

    def get_bus_list(self):
        codd_buses = list(self.cds.codd_routes.keys())
        codd_buses.sort(key=natural_sort_key)
        response = {'result': codd_buses}
        return response

    def get_bus_stops(self):
        response = {'result': [x._asdict() for x in self.cds.all_bus_stops]}
        return response

    def get_bus_stops_for_routes(self):
        response = {'result': {route_name: [x._asdict() for x in bus_stops] for (route_name, bus_stops) in
                               self.cds.bus_routes.items()}}
        return response


class TelegramDataProcessor(BaseDataProcessor):
    def __init__(self, cds: CdsRequest, logger: Logger):
        super().__init__(cds, logger)
