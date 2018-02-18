import logging
import unittest

from cds import CdsRequest

logging.basicConfig(format='%(asctime)s - %(levelname)s [%(filename)s:%(lineno)s %(funcName)20s] %(message)s',
                    level=logging.INFO,
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
        with self.subTest(f'Normal bus station order'):
            result = cds.get_dist(route_name, stop_1, stop_2)
            self.assertTrue(result)

        with self.subTest(f'Reverse bus station order'):
            result = cds.get_dist(route_name, stop_2, stop_1)
            self.assertFalse(result)

if __name__ == '__main__':
    unittest.main()
