import re
from datetime import datetime
from itertools import zip_longest

import pytz


def natural_sort_key(s, _nsre=re.compile('([0-9]+)')):
    return [int(text) if text.isdigit() else text.lower()
            for text in re.split(_nsre, s)]


def parse_routes(args):
    if not args:
        return False, tuple(), ''
    result = []
    bus_filter_start = False
    bus_filter = ''
    for i in args:
        if i in '\/|':
            bus_filter_start = True
            continue
        if bus_filter_start:
            bus_filter += i
            continue
        if result and result[-1] == 'Тр.':
            result[-1] += ' ' + i
            continue
        result.append(i)
    full_info = result[0].upper() in ['PRO', 'ПРО']
    if full_info:
        result = result[1:]

    return full_info, tuple(result), bus_filter

def distance(lat1, lon1, lat2, lon2):
    return pow(pow(lat1 - lat2, 2) + pow(lon1 - lon2, 2), 0.5)

def get_time(s):
    return pytz.utc.localize(datetime.strptime(s, '%b %d, %Y %I:%M:%S %p'))


def grouper(n, iterable, fill_value=None):
    """grouper(3, 'ABCDEFG', 'x') --> ABC DEF Gxx"""
    args = [iter(iterable)] * n
    return zip_longest(fillvalue=fill_value, *args)
