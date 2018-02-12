import unittest

import helpers


class TestFuzzySearch(unittest.TestCase):
    def test_something(self):
        f = helpers.fuzzy_search_advanced
        cases = [
            ('кирова в центр', 'ул. Кирова (в центр)', True),
            ('кирова в центр', 'ДК им. Кирова (ул. Героев Сибиряков из центра)', False),
            ('кирова в центр', 'ДК им. Кирова (ул. Героев Сибиряков из центра)', False),
            ('дк кир лен', 'ДК им. Кирова (Ленинский пр-т в сторону ул. Димитрова)', True),
            ('дк кир лен', 'ДК им. Кирова (Ленинский проспект в сторону Машмета)', True),
        ]

        for (needle, haystack, result) in cases:
            print(needle, haystack, result)
            self.assertEqual(f(needle, haystack), result)


if __name__ == '__main__':
    unittest.main()
