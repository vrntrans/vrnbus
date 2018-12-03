import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict

import fdb

from data_types import CdsRouteBus, CdsBaseDataProvider, CoddBus, LongBusRouteStop, BusStop

LOAD_TEST_DATA = False

try:
    import settings

    CDS_HOST = settings.CDS_HOST
    CDS_DB_PROJECTS_PATH = settings.CDS_DB_PROJECTS_PATH
    CDS_DB_DATA_PATH = settings.CDS_DB_DATA_PATH
    CDS_USER = settings.CDS_USER
    CDS_PASS = settings.CDS_PASS
    LOAD_TEST_DATA = settings.LOAD_TEST_DATA
except ImportError:
    settings = None
    env = os.environ
    if all((x in env for x in ("CDS_HOST", "CDS_DB_PROJECTS_PATH", "CDS_DB_DATA_PATH", "CDS_USER", "CDS_PASS",))):
        CDS_HOST = env['CDS_HOST']
        CDS_DB_PROJECTS_PATH = env['CDS_DB_PROJECTS_PATH']
        CDS_DB_DATA_PATH = env['CDS_DB_DATA_PATH']
        CDS_USER = env['CDS_USER']
        CDS_PASS = env['CDS_PASS']
    else:
        LOAD_TEST_DATA = True


class CdsDBDataProvider(CdsBaseDataProvider):
    CACHE_TIMEOUT = 30

    def __init__(self, logger):
        self.logger = logger
        self.cds_db_project = fdb.connect(host=CDS_HOST, database=CDS_DB_PROJECTS_PATH, user=CDS_USER,
                                          password=CDS_PASS, charset='WIN1251')
        self.cds_db_data = fdb.connect(host=CDS_HOST, database=CDS_DB_DATA_PATH, user=CDS_USER,
                                       password=CDS_PASS, charset='WIN1251')
        self.cds_db_project.default_tpb = fdb.ISOLATION_LEVEL_READ_COMMITED_RO
        self.cds_db_data.default_tpb = fdb.ISOLATION_LEVEL_READ_COMMITED_RO

    def try_reconnect(self):
        try:
            self.cds_db_project.close()
            self.cds_db_project = fdb.connect(host=CDS_HOST, database=CDS_DB_PROJECTS_PATH, user=CDS_USER,
                                              password=CDS_PASS, charset='WIN1251')
            self.cds_db_project.default_tpb = fdb.ISOLATION_LEVEL_READ_COMMITED_RO
            self.logger.info(f"Success connect to {CDS_HOST} {CDS_DB_PROJECTS_PATH}")
        except Exception as general_error:
            self.logger.error(general_error)

        try:
            self.cds_db_data.close()
            self.cds_db_data = fdb.connect(host=CDS_HOST, database=CDS_DB_DATA_PATH, user=CDS_USER,
                                           password=CDS_PASS, charset='WIN1251')
            self.cds_db_data.default_tpb = fdb.ISOLATION_LEVEL_READ_COMMITED_RO
            self.logger.info(f"Success connect to {CDS_HOST} {CDS_DB_DATA_PATH}")
        except Exception as general_error:
            self.logger.error(general_error)

    def now(self) -> datetime:
        return datetime.now()

    def load_codd_route_names(self) -> Dict:
        self.logger.debug('Execute fetch routes from DB')
        start = time.time()
        try:
            with fdb.TransactionContext(self.cds_db_project.trans(fdb.ISOLATION_LEVEL_READ_COMMITED_RO)) as tr:
                cur = tr.cursor()
                cur.execute('''select ID_, NAME_ from ROUTS
                                where ROUTE_ACTIVE_ = 1
                                order by NAME_''')
                self.logger.debug('Finish execution')
                result = cur.fetchallmap()
                tr.commit()
                cur.close()
                end = time.time()
                self.logger.info(f"Finish fetch data. Elapsed: {end - start:.2f}")
        except fdb.fbcore.DatabaseError as db_error:
            self.logger.error(db_error)
            self.try_reconnect()
            return {}

        result = [CoddBus(**x) for x in result]
        end = time.time()
        self.logger.info(f"Finish proccess. Elapsed: {end - start:.2f}")
        return {x.NAME_: x.ID_ for x in result}

    def load_bus_stations_routes(self) -> Dict:
        bus_routes = self.load_codd_route_names()

        bus_routes_ids = {v: k for k, v in bus_routes.items()}

        try:
            with fdb.TransactionContext(self.cds_db_project.trans(fdb.ISOLATION_LEVEL_READ_COMMITED_RO)) as tr:
                cur = tr.cursor()
                cur.execute('''select bsr.NUM as NUMBER_, bs.NAME as NAME_, bs.LAT as LAT_, 
                                bs.LON as LON_, bsr.ROUTE_ID as ROUT_, 0 as CONTROL_, bsr.BS_ID as ID
                                from BS_ROUTE bsr
                                join ROUTS r on bsr.ROUTE_ID = r.ID_
                                join BS on bsr.BS_ID = bs.ID
                                order by ROUT_, NUMBER_''')
                result = cur.fetchallmap()
                tr.commit()
                cur.close()
        except fdb.fbcore.DatabaseError as db_error:
            self.logger.error(db_error)
            self.try_reconnect()
            return {}

        long_bus_stops = [LongBusRouteStop(**x) for x in result]

        bus_stations = {}

        for stop in long_bus_stops:
            route_name = bus_routes_ids.get(stop.ROUT_, '')
            bus_list = bus_stations.get(route_name, [])
            bus_list.append(stop)
            bus_stations[route_name] = bus_list

        for (k, v) in bus_stations.items():
            v.sort(key=lambda tup: tup.NUMBER_)

        return bus_stations

    def load_all_cds_buses(self) -> List[CdsRouteBus]:
        def make_names_lower(x):
            return {k.lower(): v for (k, v) in x.iteritems()}

        self.logger.debug('Execute fetch all from DB')
        start = time.time()
        try:
            with fdb.TransactionContext(self.cds_db_project.trans(fdb.ISOLATION_LEVEL_READ_COMMITED_RO)) as tr:
                cur = tr.cursor()
                cur.execute('''SELECT bs.NAME_ AS BUS_STATION_, rt.NAME_ AS ROUTE_NAME_,  o.NAME_, o.OBJ_ID_, o.LAST_TIME_,
                    o.LAST_LON_, o.LAST_LAT_, o.LAST_SPEED_, o.LAST_STATION_TIME_, o.PROJ_ID_,
                     coalesce(o.lowfloor, 0) as low_floor, coalesce(o.VEHICLE_TYPE_, 0) as bus_type,
                      coalesce(obj_output_, 0) as obj_output 
                    FROM OBJECTS O LEFT JOIN BUS_STATIONS bs
                    ON o.LAST_ROUT_ = bs.ROUT_ AND o.LAST_STATION_ = bs.NUMBER_
                    LEFT JOIN ROUTS rt ON o.LAST_ROUT_ = rt.ID_''')
                self.logger.debug('Finish execution')
                result = cur.fetchallmap()
                tr.commit()
                cur.close()
                end = time.time()
                self.logger.info(f"Finish fetch data. Elapsed: {end - start:.2f}")
        except fdb.fbcore.DatabaseError as db_error:
            self.logger.error(db_error)
            self.try_reconnect()
            return []

        result = [CdsRouteBus(**make_names_lower(x)) for x in result]
        result.sort(key=lambda s: s.last_time_, reverse=True)
        end = time.time()
        self.logger.info(f"Finish proccess. Elapsed: {end - start:.2f}")
        return result

    def load_bus_stops(self) -> List[BusStop]:
        self.logger.debug('Execute load_bus_stops from DB')
        start = time.time()
        try:
            with fdb.TransactionContext(self.cds_db_project.trans(fdb.ISOLATION_LEVEL_READ_COMMITED_RO)) as tr:
                cur = tr.cursor()
                cur.execute('''select distinct  ID, NAME as NAME_, LAT as LAT_, LON as LON_
                            from bs
                            order by NAME_''')
                self.logger.debug('Finish execution')
                result = cur.fetchallmap()
                tr.commit()
                cur.close()
                end = time.time()
                self.logger.info(f"Finish fetch data. Elapsed: {end - start:.2f}")
        except fdb.fbcore.DatabaseError as db_error:
            self.logger.error(db_error)
            self.try_reconnect()
            return []

        return [BusStop(**x) for x in result]


class CdsTestDataProvider(CdsBaseDataProvider):
    CACHE_TIMEOUT = 0.0001

    def __init__(self, logger):
        self.logger = logger
        self.test_data_files = []
        self.test_data_index = 0
        self.mocked_now = datetime.now()
        self.load_test_data()

    def load_test_data(self):
        self.test_data_files = sorted(Path('./test_data/').glob('codd_data_db*.json'))
        self.test_data_index = 0
        if self.test_data_files:
            path = self.test_data_files[0]
            self.mocked_now = datetime.strptime(path.name, "codd_data_db%y_%m_%d_%H_%M_%S.json")
        else:
            raise Exception("Cannot load test data from ./test_data/")

    def load_codd_route_names(self) -> Dict:
        my_file = Path("bus_routes_codd.json")
        with open(my_file, 'rb') as f:
            return json.load(f)

    def now(self):
        if self.test_data_files and self.test_data_index >= len(self.test_data_files):
            self.test_data_index = 0
        path = self.test_data_files[self.test_data_index]
        self.mocked_now = datetime.strptime(path.name, "codd_data_db%y_%m_%d_%H_%M_%S.json")
        return self.mocked_now

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

    def load_all_cds_buses(self) -> List[CdsRouteBus]:
        return self.next_test_data()

    def load_bus_stations_routes(self) -> Dict:
        with open(Path("bus_stations.json"), 'rb') as f:
            bus_stations = json.load(f)

        result = {}
        for k, v in bus_stations.items():
            route = [LongBusRouteStop(*i) for i in v]
            route.sort(key=lambda tup: tup.NUMBER_)
            result[k] = route

        return result

    def load_bus_stops(self) -> List[BusStop]:
        with open('bus_stops.json', 'rb') as f:
            return [BusStop(**i) for i in json.load(f)]


class StubDataProvider(CdsBaseDataProvider):
    CACHE_TIMEOUT = 0

    def now(self) -> datetime:
        return datetime.now()

    def load_all_cds_buses(self) -> List[CdsRouteBus]:
        return []

    def load_codd_route_names(self) -> Dict:
        return {}

    def load_bus_stations_routes(self) -> Dict:
        return {}

    def load_bus_stops(self) -> List[BusStop]:
        return []

def get_data_provider(logger):
    try:
        return CdsTestDataProvider(logger) if LOAD_TEST_DATA else CdsDBDataProvider(logger)
    except Exception as ex:
        logger.exception(ex)
        return StubDataProvider()

