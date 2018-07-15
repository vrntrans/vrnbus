import datetime
from enum import Enum
from typing import NamedTuple, List, Dict

from helpers import distance_km, distance, get_iso_time


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
    CONTROL_: int = 0

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
    last_time: datetime.datetime

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
    last_time_: datetime.datetime
    name_: str
    obj_id_: int
    proj_id_: int
    route_name_: str
    type_proj: int = 0
    last_station_time_: datetime.datetime = None
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


class CdsBaseDataProvider:
    CACHE_TIMEOUT = 0

    def now(self) -> datetime.datetime:
        pass

    def load_all_cds_buses(self) -> List[CdsRouteBus]:
        pass

    def load_codd_route_names(self) -> Dict:
        pass

    def load_bus_stations_routes(self) -> Dict:
        pass


class AbuseRule(NamedTuple):
    event: Enum
    count: int
    delta: datetime.timedelta


class StatsData(NamedTuple):
    min10: int
    min30: int
    min60: int
    total: int
    text: str
