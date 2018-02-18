import logging
import unittest

from cds import CdsRequest, CdsRouteBus, CdsBusPosition
from helpers import get_iso_time

logging.basicConfig(format='%(asctime)s - %(levelname)s [%(filename)s:%(lineno)s %(funcName)20s] %(message)s',
                    level=logging.DEBUG,
                    handlers=[logging.StreamHandler()])

logger = logging.getLogger("vrnbus")

cds = CdsRequest(logger)


class CdsTestCase(unittest.TestCase):
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
        route_bus = CdsRouteBus.make(*[
            51.705497, 39.149543,
            16,
            "2018-02-15T19:57:47",
            "Н990ХЕ36",
            834,
            20,
            "5А",
            0,
            "2018-02-15T19:54:56",
            "Рабочий проспект (из центра)",
            None
        ])

        bus_positions = [
            # CdsBusPosition(51.705497, 39.149543, get_iso_time("2018-02-15T19:57:47")), # у-м Молодёжный
                         CdsBusPosition(51.705763, 39.155278, get_iso_time("2018-02-15T19:57:47")), #60 лет ВЛКСМ
                         ]


        with self.subTest('From city center '):
            result = cds.get_closest_bus_stop_checked(route_bus, bus_positions)
            self.assertTrue(result.NAME_ == 'у-м Молодежный (ул. Лизюкова из центра)')
            self.assertTrue(result.NUMBER_ == 61)


if __name__ == '__main__':
    unittest.main()
