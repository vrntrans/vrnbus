import datetime
import json
import logging
import math
import re
import time
from functools import wraps
from itertools import zip_longest
from typing import NamedTuple

import pytz

QUICK_FIX_DIST = 10000

class CustomJsonEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, datetime.datetime):
            return o.isoformat()
        if isinstance(o, set):
            return list(o)
        return json.JSONEncoder.default(self, o)


class SearchResult(NamedTuple):
    full_info: bool = False
    bus_routes: tuple = tuple()
    bus_filter: str = ''
    all_buses: bool = False


tz = pytz.timezone('Europe/Moscow')
logger = logging.getLogger("vrnbus")


def natural_sort_key(s, _nsre=re.compile('([0-9]+)')):
    return [int(text) if text.isdigit() else text.lower()
            for text in re.split(_nsre, s)]


def parse_routes(text):
    if not text:
        return SearchResult()._replace(all_buses=True)
    if isinstance(text, (list, tuple,)):
        text = ' '.join(text)
    args = re.split("[ ,;]+", text)
    if not args:
        return SearchResult()
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
        result.append(i)
    if not result:
        return SearchResult(bus_filter=bus_filter)
    full_info = result[0].upper() in ['PRO', 'ПРО']
    if full_info:
        result = result[1:]

    return SearchResult(full_info, tuple(result), bus_filter)


def distance(lat1, lon1, lat2, lon2):
    if not all((lat1, lon1, lat2, lon2)):
        return QUICK_FIX_DIST
    return ((lat1 - lat2) ** 2 + (lon1 - lon2) ** 2) ** 0.5


def azimuth(glon1, glat1, glon2, glat2):
    if not all((glon1, glat1, glon2, glat2)):
        return QUICK_FIX_DIST
    lat1 = glat1 * math.pi / 180
    lat2 = glat2 * math.pi / 180
    long1 = glon1 * math.pi / 180
    long2 = glon2 * math.pi / 180
    cosl1 = math.cos(lat1)
    cosl2 = math.cos(lat2)
    sinl1 = math.sin(lat1)
    sinl2 = math.sin(lat2)
    delta = long2 - long1
    cdelta = math.cos(delta)
    sdelta = math.sin(delta)
    x = (cosl1 * sinl2) - (sinl1 * cosl2 * cdelta)
    y = sdelta * cosl2
    z = (math.atan(-y / x)) / 0.017453293
    if (x < 0):
        z = z + 180
    z2 = (z + 180) % 360 + 180
    z2 = -(z2 * 0.017453293)
    anglerad2 = z2 - ((2 * math.pi) * math.floor(z2 / (2 * math.pi)))
    angledeg = (anglerad2 * 180) / math.pi
    azmth = round(angledeg)

    return azmth


def parse_int(s, default=0):
    try:
        return int(s), True
    except Exception:
        return default, False


def distance_km(glat1, glon1, glat2, glon2):
    if not all((glat1, glon1, glat2, glon2)):
        return QUICK_FIX_DIST
    r = 6373.0

    lat1 = math.radians(glat1)
    lon1 = math.radians(glon1)
    lat2 = math.radians(glat2)
    lon2 = math.radians(glon2)

    diff_lon = lon2 - lon1
    diff_lat = lat2 - lat1

    a = math.sin(diff_lat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(diff_lon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    result = r * c
    return result


def get_iso_time(s) -> datetime.datetime:
    if isinstance(s, datetime.datetime):
        return s

    try:
        return datetime.datetime.strptime(s, '%Y-%m-%dT%H:%M:%S.%f')
    except ValueError:
        return datetime.datetime.strptime(s, '%Y-%m-%dT%H:%M:%S')


def get_time(s):
    if isinstance(s, datetime.datetime):
        return tz.localize(s)
    return tz.localize(datetime.datetime.strptime(s, '%b %d, %Y %I:%M:%S %p'))


def grouper(n, iterable, fill_value=None):
    """grouper(3, 'ABCDEFG', 'x') --> ABC DEF Gxx"""
    args = [iter(iterable)] * n
    return zip_longest(fillvalue=fill_value, *args)


def retry_multi(max_retries=5):
    """ Retry a function `max_retries` times. """

    def retry(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            num_retries = 0
            ret = None
            while num_retries <= max_retries:
                try:
                    ret = func(*args, **kwargs)
                    break
                except Exception as e:
                    logger.exception(e)
                    if num_retries == max_retries:
                        raise
                    num_retries += 1
                    time.sleep(5)
            return ret

        return wrapper

    return retry


def fuzzy_search(needle: str, haystack: str) -> bool:
    hlen = len(haystack)
    nlen = len(needle)
    needle = needle.lower()
    haystack = haystack.lower()
    if nlen > hlen or nlen == 0:
        return False
    if needle in haystack:
        return True
    position = 0
    for i in range(nlen):
        nch = needle[i]
        position = haystack.find(nch, position) + 1
        if position == 0:
            return False
    return True


def fuzzy_search_advanced(needle: str, haystack: str) -> bool:
    hlen = len(haystack)
    nlen = len(needle)
    needle = needle.lower()
    haystack = haystack.lower()
    if nlen > hlen or nlen == 0:
        return False

    if needle in haystack:
        return True

    nch = needle[0]
    position = haystack.find(nch)
    if position == -1:
        return False

    skip_chars = (' ', ',', '(', ')', '.')
    if position > 0 and nch not in skip_chars:
        while True:
            position = haystack.find(nch, position) + 1
            if position == 0:
                return False
            if haystack[position - 2] in skip_chars:
                break

    i = 1
    while i < nlen:
        nch = needle[i]
        prev_position = position + 1
        position = haystack.find(nch, position) + 1

        if position == 0:
            return False

        skip_pos = position - prev_position

        if skip_pos > 0 and haystack[position - 2] not in skip_chars and nch not in skip_chars and i > 1:
            i -= 1
            continue

        i += 1

    return True
