import re
from datetime import datetime
from itertools import zip_longest


def natural_sort_key(s, _nsre=re.compile('([0-9]+)')):
    return [int(text) if text.isdigit() else text.lower()
            for text in re.split(_nsre, s)]


def parse_routes(args):
    if not args:
        return (False, tuple(), '')
    result = []
    filter_start = False
    filter = ''
    for i in args:
        if i in '\/|':
            filter_start = True
            continue
        if filter_start:
            filter += i
            continue
        if result and result[-1] == 'Тр.':
            result[-1] += ' ' + i
            continue
        result.append(i)
    full_info = result[0].upper() in ['PRO', 'ПРО']
    if full_info:
        result = result[1:]

    return (full_info, tuple(result), filter)


def get_time(s):
    return datetime.strptime(s, '%b %d, %Y %I:%M:%S %p')


def grouper(n, iterable, fillvalue=None):
    "grouper(3, 'ABCDEFG', 'x') --> ABC DEF Gxx"
    args = [iter(iterable)] * n
    return zip_longest(fillvalue=fillvalue, *args)
