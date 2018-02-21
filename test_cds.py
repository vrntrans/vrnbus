import datetime
import logging
import unittest

from cds import CdsRequest
from data_types import CdsBusPosition

logging.basicConfig(format='%(asctime)s - %(levelname)s [%(filename)s:%(lineno)s %(funcName)20s] %(message)s',
                    level=logging.DEBUG,
                    handlers=[logging.StreamHandler()])

logger = logging.getLogger("vrnbus")

cds = CdsRequest(logger)


class CdsTestCase(unittest.TestCase):
    date_time = datetime.datetime(2018, 2, 15, 19, 56, 53)

    def test_routes_on_bus_stop(self):
        result = cds.get_routes_on_bus_stop('у-м Молодежный (ул. Лизюкова в центр)')
        self.assertTrue(result)

    def test_bus_stop_distance(self):
        route_name = "5А"
        stop_1 = "у-м Молодежный (ул. Лизюкова в центр)"
        stop_2 = "ул. Лизюкова (ул. Жукова в центр)"

        with self.subTest('Normal bus station order'):
            result = cds.get_dist(route_name, stop_1, stop_2)
            self.assertTrue(result)

        with self.subTest('Reverse bus station order'):
            result = cds.get_dist(route_name, stop_2, stop_1)
            self.assertFalse(result)

    def test_closest_bus_stop_checked(self):
        route_name = '5А'
        pos_1 = CdsBusPosition(51.705497, 39.149543, self.date_time)  # у-м Молодёжный
        pos_2 = CdsBusPosition(51.705763, 39.155278, self.date_time)  # 60 лет ВЛКСМ

        with self.subTest('From city center '):
            result = cds.get_closest_bus_stop_checked(route_name, (pos_2, pos_1))
            self.assertTrue(result.NAME_ == 'у-м Молодежный (ул. Лизюкова из центра)')
            self.assertTrue(result.NUMBER_ == 61)

        with self.subTest('To city center '):
            result = cds.get_closest_bus_stop_checked(route_name, (pos_1, pos_2))
            self.assertTrue(result.NUMBER_ == 4)

    def test_closest_bus_stop_same_stations(self):
        positions = [CdsBusPosition(51.667033, 39.193648, self.date_time),
                     CdsBusPosition(51.672135, 39.187541, self.date_time),
                     CdsBusPosition(51.675065, 39.185286, self.date_time),
                     CdsBusPosition(51.677922, 39.184953, self.date_time),
                     CdsBusPosition(51.677922, 39.184953, self.date_time),
                     CdsBusPosition(51.680843, 39.184798, self.date_time)]

        result = cds.get_closest_bus_stop_checked("90", positions)

        self.assertTrue(result.NUMBER_ == 40)
        self.assertTrue(result.NAME_ == 'Проспект Труда (Московский проспект из центра)')


if __name__ == '__main__':
    unittest.main()
