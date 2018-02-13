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


tz = pytz.timezone('Europe/Moscow')
logger = logging.getLogger("vrnbus")


def natural_sort_key(s, _nsre=re.compile('([0-9]+)')):
    return [int(text) if text.isdigit() else text.lower()
            for text in re.split(_nsre, s)]


def parse_routes(text):
    if not text:
        return SearchResult()
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
    return ((lat1 - lat2) ** 2 + (lon1 - lon2) ** 2) ** 0.5


def distance_km(glat1, glon1, glat2, glon2):
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
    return datetime.datetime.strptime(s, "%Y-%m-%dT%H:%M:%S")


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
                    logger.error(e)
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
            if haystack[position - 1] not in skip_chars:
                position = haystack.find(nch, position) + 1
                if position == 0:
                    return False
            else:
                break

    i = 1
    while i < nlen :
        nch = needle[i]
        prev_position = position + 1
        position = haystack.find(nch, position) + 1

        if position == 0:
            return False

        distance_search = position - prev_position

        if distance_search > 0 and haystack[position - 2] not in skip_chars and nch not in skip_chars and i > 1:
            i -= 1
            continue

        i += 1

    return True