import datetime
from enum import Enum
from typing import NamedTuple, List, Dict, Union

from helpers import distance_km, distance, get_iso_time, QUICK_FIX_DIST


class UserLoc(NamedTuple):
    lat: float
    lon: float


class BusStop(NamedTuple):
    NAME_: str
    LAT_: float
    LON_: float
    ID: int
    AZMTH: int = 0

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
    ID: int = 0

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
    lat: float
    lon: float
    last_time: datetime.datetime

    def distance(self, bus_stop: BusStop = None, user_loc: UserLoc = None):
        if not bus_stop and not user_loc:
            return QUICK_FIX_DIST
        (lat, lon) = (bus_stop.LAT_, bus_stop.LON_) if bus_stop else (user_loc.lat, user_loc.lon)
        if lat is None or lon is None:
            return QUICK_FIX_DIST
        return distance(lat, lon, self.lat, self.lon)

    def distance_km(self, bus_stop: BusStop = None, position: Union[UserLoc, NamedTuple] = None):
        (lat, lon) = (bus_stop.LAT_, bus_stop.LON_) if bus_stop else (position.lat, position.lon)
        if lat is None or lon is None:
            return QUICK_FIX_DIST
        return distance_km(lat, lon, self.lat, self.lon)

    def is_valid_coords(self):
        return self.lat != 0.0 and self.lon != 0.0


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
    bus_station_: str = ""
    low_floor: bool = False
    bus_type: int = 0
    obj_output: int = 0
    avg_speed: float = 0
    avg_last_speed: float = 0
    azimuth: int = 0

    @staticmethod
    def make(last_lat_, last_lon_, last_speed_, last_time_, name_, obj_id_, proj_id_, route_name_,
             type_proj, last_station_time_, bus_station_, low_floor=False, bus_type=0, avg_speed=18, azimuth=0):
        try:
            last_time_ = get_iso_time(last_time_)
            last_station_time_ = get_iso_time(last_station_time_) if last_station_time_ else None
        except Exception as e:
            print(e)
        return CdsRouteBus(last_lat_, last_lon_, last_speed_, last_time_, name_, obj_id_, proj_id_,
                           route_name_, type_proj, last_station_time_, bus_station_, low_floor, bus_type, avg_speed, azimuth)

    def get_bus_position(self) -> CdsBusPosition:
        return CdsBusPosition(self.last_lat_, self.last_lon_, self.last_time_)

    def filter_by_name(self, filter_query: str) -> bool:
        bus_filter = filter_query.lower().split(' ')
        name = self.name_.lower()
        return not filter_query or any((q in name for q in bus_filter if q))

    def short(self):
        return f'{self.bus_station_}; {self.last_lat_} {self.last_lon_} '

    def distance(self, bus_stop: BusStop = None, user_loc: UserLoc = None):
        if not bus_stop and not user_loc:
            return QUICK_FIX_DIST
        (lat, lon) = (bus_stop.LAT_, bus_stop.LON_) if bus_stop else (user_loc.lat, user_loc.lon)
        return distance(lat, lon, self.last_lat_, self.last_lon_)

    def distance_km(self, bus_stop: BusStop = None, user_loc: UserLoc = None):
        if not bus_stop and not user_loc:
            return QUICK_FIX_DIST
        (lat, lon) = (bus_stop.LAT_, bus_stop.LON_) if bus_stop else (user_loc.lat, user_loc.lon)
        return distance_km(lat, lon, self.last_lat_, self.last_lon_)

    def is_valid_coords(self):
        return self.last_lat_ > 0.0 and self.last_lon_ > 0.0


class ArrivalBusStopInfo(NamedTuple):
    bus_info: CdsRouteBus
    distance: float
    time_left: float


class ArrivalBusStopInfoFull(NamedTuple):
    bus_stop_id: int
    bus_stop_name: str
    lat: float
    lon: float
    text: str
    bus_routes: List[str] = []
    arrival_buses: List[ArrivalBusStopInfo] = []


class ArrivalInfo(NamedTuple):
    text: str
    header: str = ''
    arrival_details: List[ArrivalBusStopInfoFull] = []
    bus_stops: List[BusStop] = []
    found: bool = False


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

    def load_bus_stops(self) -> List[BusStop]:
        pass

    def load_new_codd_route_names(self):
        pass

    def load_new_bus_stations_routes(self):
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
