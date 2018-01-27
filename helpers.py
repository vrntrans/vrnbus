import math
import re
from datetime import datetime
from itertools import zip_longest

import pytz

tz = pytz.timezone('Europe/Moscow')

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

def distance_km(lat1, lon1, lat2, lon2):
    R = 6373.0

    lat1 = math.radians(lat1)
    lon1 = math.radians(lon1)
    lat2 = math.radians(lat2)
    lon2 = math.radians(lon2)

    dlon = lon2 - lon1
    dlat = lat2 - lat1

    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    result = R * c
    return result

def get_time(s):
    return tz.localize(datetime.strptime(s, '%b %d, %Y %I:%M:%S %p'))

def grouper(n, iterable, fill_value=None):
    """grouper(3, 'ABCDEFG', 'x') --> ABC DEF Gxx"""
    args = [iter(iterable)] * n
    return zip_longest(fillvalue=fill_value, *args)
