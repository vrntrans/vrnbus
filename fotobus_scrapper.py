import re
import time

import requests
from bs4 import BeautifulSoup

fb_name_re = re.compile(r"(\D+)(\d+)(\D+)(\d+)")

def get_name_with_spaces(bus_name):
    match = fb_name_re.match(bus_name)
    if not match:
        return
    return " ".join(match.groups())

def get_url(bus_name):
    name_w_spaces = get_name_with_spaces(bus_name)
    if not name_w_spaces:
        return
    return "http://fotobus.msk.ru/ajax2.php?action=index-qsearch&cid=0&type=1&num=" + name_w_spaces

def get_bus_search_page(bus_name):
    url = get_url(bus_name)
    if not url:
        return

    result = requests.get(url)
    return result.content

def get_fb_links(content):
    soup = BeautifulSoup(content, features="html.parser")
    anchors = soup.find_all("a")
    hrefs = {a.get('href').split('#')[0] for a in anchors}
    return [f"http://fotobus.msk.ru{h}" for h in hrefs]


def fb_links(name):
    content = get_bus_search_page(name)
    return get_fb_links(content)


if __name__ == '__main__':
    start = time.time()
    content = get_bus_search_page("Е312УС36")
    result = get_fb_links(content)
    print(result)
    print(time.time() - start)