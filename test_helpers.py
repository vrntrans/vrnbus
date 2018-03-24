import unittest

import helpers


class TestFuzzySearch(unittest.TestCase):
    def test_different_cases(self):
        f = helpers.fuzzy_search_advanced
        cases = [
            ('кирова в центр', 'ул. Кирова (в центр)', True),
            ('кирова', 'ул. Кирова (в центр)', True),
            ('кирова', 'ДК им. Кирова (ул. Героев Сибиряков из центра)', True),
            ('кирова в центр', 'ДК им. Кирова (ул. Героев Сибиряков из центра)', False),
            ('кирова в центр', 'ДК им. Кирова (ул. Героев Сибиряков из центра)', False),
            ('дк кир лен', 'ДК им. Кирова (Ленинский пр-т в сторону ул. Димитрова)', True),
            ('дк кир лен', 'ДК им. Кирова (Ленинский проспект в сторону Машмета)', True),
            ('брно', 'Мебель Черноземья (в центр)', False),
            ('автовокзал в', 'автовокзал (в центр)', True),
            ('автовокзал в', 'Центральный автовокзал (в центр)', True),
        ]

        for (needle, haystack, result) in cases:
            with self.subTest(f'{needle}, {haystack}, {result}'):
                self.assertEqual(f(needle, haystack), result)


class TestGeoFunction(unittest.TestCase):
    def test_azimuth(self):
        f = helpers.azimuth
        cases = [
            ((24.323810, 1.368795, 39.169720, 51.652228), 12),
            ((241.323810, 1.468795, 39.182616, 51.697372), 16),
        ]

        for (params, result) in cases:
            with self.subTest(f'{params}, {result}'):
                self.assertEqual(f(*params), result)



if __name__ == '__main__':
    unittest.main()
