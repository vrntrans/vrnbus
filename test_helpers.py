import unittest

import helpers


class TestFuzzySearch(unittest.TestCase):
    def test_something(self):
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
        ]

        for (needle, haystack, result) in cases:
            with self.subTest(f'{needle}, {haystack}, {result}'):
                self.assertEqual(f(needle, haystack), result)


class TestBusStopCalc(unittest.TestCase):
    pass

if __name__ == '__main__':
    unittest.main()
