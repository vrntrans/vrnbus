# #!/usr/bin/env python3.6
import codecs
import json
import logging
import os
from datetime import datetime
from datetime import timedelta
from itertools import groupby, zip_longest
from pathlib import Path

import cachetools.func
import requests
import telegram
from telegram import ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackQueryHandler


def get_time(s):
    return datetime.strptime(s, '%b %d, %Y %I:%M:%S %p')


# Enable logging
logging.basicConfig(format='%(asctime)s - %(levelname)s [%(filename)s:%(lineno)s %(funcName)20s] %(message)s',
                    level=logging.INFO)

logger = logging.getLogger(__name__)
cds_url_base = 'http://195.98.79.37:8080/CdsWebMaps/'
codd_base_usl = 'http://195.98.83.236:8080/CitizenCoddWebMaps/'
cookies = {'JSESSIONID': 'C8ED75C7EC5371CBE836BDC748BB298F', 'session_id': 'vrntrans'}
fake_header = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
                  'Chrome/63.0.3239.132 Safari/537.36'}

logger.info(os.environ)
if 'DYNO' in os.environ:
    debug = False
else:
    debug = True

import re


def natural_sort_key(s, _nsre=re.compile('([0-9]+)')):
    return [int(text) if text.isdigit() else text.lower()
            for text in re.split(_nsre, s)]


def init_routes():
    my_file = Path("bus_routes.json")
    if my_file.is_file():
        with open(my_file, 'rb') as f:
            routes_base_local = json.load(f)
    else:
        routes_base_local = load_bus_routes()
    print('finished init_routes')
    return routes_base_local


def init_bus_stops():
    with open('bus_stops.json', 'rb') as f:
        result = json.load(f)
    print('finished init_bus_stops')
    return result


def parse_routes(args):
    result = []
    for i in args:
        if result and result[-1] == 'Тр.':
            result[-1] += ' ' + i
            continue
        result.append(i)
    return result


routes_base = init_routes()
bus_stops = init_bus_stops()
user_settings = {}


@cachetools.func.ttl_cache()
def get_all_buses():
    def key_check(x):
        return 'name_' in x and 'last_time_' in x and (now - get_time(x['last_time_'])) < hour
    r = requests.get(f'{cds_url_base}GetBuses', cookies=cookies, headers=fake_header)
    logger.info(f"{r.url} {r.elapsed}")
    if r.text:
        result = json.loads(r.text)
        now = datetime.now()
        hour = timedelta(hours=1)
        short_result = [(d['name_'], d['last_time_'], d['route_name_'], d['proj_id_']) for d in result if key_check(d)]
        short_result = sorted(short_result, key=lambda x: natural_sort_key(x[2]))
        grouped = [(k, len(list(g))) for k, g in groupby(short_result, lambda x: f'{x[2]} ({x[3]})')]
        if short_result:
            buses = ' \n'.join((('{} => {}'.format(i[0], i[1])) for i in grouped))
            return buses

    return 'Ничего не нашлось'


@cachetools.func.ttl_cache(ttl=60)
def bus_request_as_list(bus_route):
    url = f'{cds_url_base}GetRouteBuses'
    if not bus_route:
        return []
    keys = [x for x in routes_base.keys() for r in bus_route if x.upper() == r.upper()]
    routes = [{'proj_ID': routes_base.get(k), 'route': k} for k in keys]
    if not routes:
        return []
    payload = {'routes': json.dumps(routes)}
    logger.info(f"bus_request_as_list {routes}")
    r = requests.post(url, cookies=cookies, data=payload, headers=fake_header)
    logger.info(f"{r.url} {payload} {r.elapsed}")

    if r.text:
        logger.debug(r.text)
        result = json.loads(r.text)
        now = datetime.now()
        hour = timedelta(hours=1)
        key_check = lambda x: 'name_' in x and 'last_time_' in x and (now - get_time(x['last_time_'])) < hour
        short_result = sorted([d for d in result if key_check(d)], key=lambda s:natural_sort_key(s['route_name_']))
        return short_result
    return []


@cachetools.func.ttl_cache(ttl=60)
def bus_request(bus_route):
    print('bus_route', bus_route)
    if not bus_route:
        return 'Не заданы маршруты'
    short_result = bus_request_as_list(bus_route)
    if short_result:
        print(short_result)
        stations = ' \n'.join(
            f"{d['route_name_']}, {get_time(d['last_time_']):%H:%M}, {d.get('bus_station_')}" for d in short_result)
        return stations

    return 'Ничего не нашлось'


@cachetools.func.ttl_cache(ttl=60)
def bus_request_pro(bus_route):
    print('bus_route', bus_route)
    if not bus_route:
        return 'Не заданы маршруты'
    short_result = bus_request_as_list(bus_route)

    if short_result:
        print(short_result)
        stations = ' \n'.join(
            f"{d['route_name_']} {get_time(d['last_time_']):%H:%M} {d.get('bus_station_')} {d['name_']} " for d in
            short_result)
        print(stations)
        return stations

    return 'Ничего не нашлось'


@cachetools.func.ttl_cache(ttl=90)
def next_bus_for_lat_lon(lat, lon):
    url = f'{codd_base_usl}GetNextBus'
    payload = {'lat': lat, 'lon': lon}
    r = requests.post(url, data=payload, headers=fake_header)
    logger.info(f"{r.url} {payload} {r.elapsed}")
    if r.text:
        result = json.loads(r.text)
        return result


@cachetools.func.ttl_cache(ttl=90)
def next_bus(bus_stop, user_bus_list):
    bus_stop = ' '.join(bus_stop)
    bus_stop_matches = [x for x in bus_stops if bus_stop.upper() in x['NAME_'].upper()]
    print(bus_stop, bus_stop_matches)
    if not bus_stop_matches:
        return f'Остановки c именем "{bus_stop}" не найдены'
    if len(bus_stop_matches) > 5:
        first_matches = '\n'.join([x['NAME_'] for x in bus_stop_matches[:20]])
        return f'Уточните остановку. Найденные варианты:\n{first_matches}'
    return next_bus_for_matches(bus_stop_matches, user_bus_list)


# @cachetools.func.ttl_cache(ttl=60)
def next_bus_for_matches(bus_stop_matches, user_bus_list):
    result = []
    if user_bus_list:
        result.append(f"Фильтр по маршрутам: {' '.join(user_bus_list)}. Настройка: /settings")
    for item in bus_stop_matches:
        arrivals = next_bus_for_lat_lon(item['LAT_'], item['LON_'])
        if arrivals:
            header = arrivals[0]
            items = [x for x in arrivals[1:] if x['time_'] > 0 and (not user_bus_list or x["rname_"].strip() in user_bus_list)]
            items.sort(key=lambda s: natural_sort_key(s['rname_']))
            if not items:
                result.append(f'Остановка {header["rname_"]}: нет данных')
                continue
            next_bus_info = f"Остановка {header['rname_']}:\n"
            next_bus_info += '\n'.join((f"{x['rname_']} - {x['time_']} мин" for x in items))
            result.append(next_bus_info)
    return '\n'.join(result)


def last_buses(bot, update, args):
    """Send a message when the command /last is issued."""
    user = update.message.from_user
    logger.info(f"last_buses. User: {user}; {args}")
    routes = parse_routes(args)
    response = bus_request(tuple(routes))
    logger.info(f"last_buses. User: {user}; Response {response}")
    update.message.reply_text(response)


def last_buses_pro(bot, update, args):
    """Send a message when the command /start is issued."""
    user = update.message.from_user
    logger.info(f"last_buses_pro. User: {user}; {args}")
    routes = parse_routes(args)
    response = bus_request_pro(tuple(routes))
    update.message.reply_text(response)


def next_bus_handler(bot, update, args):
    """Send a message when the command /start is issued."""
    user = update.message.from_user
    logger.info(f"next_bus_handler. User: {user}; {args}")
    if not args:
        location_btn = telegram.KeyboardButton(text="Местоположение", request_location=True)
        cancel_btn = telegram.KeyboardButton(text="Отмена")
        custom_keyboard = [[location_btn, cancel_btn]]
        reply_markup = telegram.ReplyKeyboardMarkup(custom_keyboard, one_time_keyboard=True)
        update.message.reply_text("""Не указана остановка, попробуйте указать местоположение""",
                                  reply_markup=reply_markup)
        return

    settings = user_settings.get(user.id, [])
    response = next_bus(tuple(args), tuple(settings))
    update.message.reply_text(response)


def stats(bot, update):
    """Send a message when the command /stats is issued."""
    user = update.message.from_user
    logger.info(f"Stats. User: {user}")
    response = get_all_buses()
    update.message.reply_text(response)


def help(bot, update):
    """Send a message when the command /help is issued."""
    update.message.reply_text("""/last номера маршрутов через пробел - последние остановки
/nextbus имя остановки - ожидаемое время прибытия""", reply_markup=ReplyKeyboardRemove())


def start(bot, update):
    """Send a message when the command /help is issued."""
    user = update.message.from_user
    logger.info(f"start. User: {user};")

    location_keyboard = telegram.KeyboardButton(text="Местоположение", request_location=True)
    cancel_button = telegram.KeyboardButton(text="Отмена")
    custom_keyboard = [[location_keyboard, cancel_button]]
    reply_markup = telegram.ReplyKeyboardMarkup(custom_keyboard, one_time_keyboard=True)
    update.message.reply_text("/last номера маршрутов через пробел - последние остановки\n"
                              "/nextbus имя остановки - ожидаемое время прибытия", reply_markup=reply_markup)


def echo(bot, update):
    """Echo the user message."""
    update.message.reply_text(update.message.text, reply_markup=ReplyKeyboardRemove())


def error(bot, update, error):
    """Log Errors caused by Updates."""
    logger.warning('Update "%s" caused error "%s"', update, error)


@cachetools.func.ttl_cache()
def matches_bus_stops(lat, lon, size=3):
    distance = lambda item: pow(pow(item['LON_'] - lat, 2) + pow(item['LAT_'] - lon, 2), 0.5)
    return sorted(bus_stops, key=distance)[:size]


def location(bot, update):
    user = update.message.from_user
    user_location = update.message.location
    logger.info("Location of %s: %f / %f", user.first_name, user_location.latitude,
                user_location.longitude)
    matches = matches_bus_stops(user_location.latitude, user_location.longitude)

    settings = user_settings.get(user.id, [])
    result = next_bus_for_matches(matches, settings)
    logger.info(f"next_bus_for_matches {user} {result}")
    update.message.reply_text(result, reply_markup=ReplyKeyboardRemove())



def grouper(n, iterable, fillvalue=None):
  "grouper(3, 'ABCDEFG', 'x') --> ABC DEF Gxx"
  args = [iter(iterable)] * n
  return zip_longest(fillvalue=fillvalue, *args)

def get_buttons_routes(user_routes):
    #TODO: too many buttons
    routes_list = sorted(list(routes_base.keys()), key=natural_sort_key)
    routes_groups = list(grouper(8, routes_list))
    route_btns = [[InlineKeyboardButton('Hide', callback_data='hide')],
                  [InlineKeyboardButton('All', callback_data='all'),
                   InlineKeyboardButton('None', callback_data='none')]
                  ] + [
        [InlineKeyboardButton(f"{x}{'+' if x in user_routes else ''}", callback_data=x)
         for x in group if x]
        for group in routes_groups]
    keyboard = route_btns + [
                ]
    return keyboard

def itest(bot, update, args):
    user_id = user = update.message.from_user.id
    settings = user_settings.get(user_id, [])
    settings_routes = parse_routes(args)
    if settings_routes:
        cmd = settings_routes[0]
        items = settings_routes[1:]
        if len(settings_routes) == 1 and cmd in ('all', 'none'):
                settings = []
        elif cmd == 'del':
            settings = [x for x in settings if x not in items]
        elif cmd == 'add':
            settings += [x for x in items if x in routes_base.keys() and x not in settings]
        else:
            settings = [x for x in settings_routes if x in routes_base.keys()]
        user_settings[user_id] = settings
        update.message.reply_text(f"Текущие маршруты для вывода: {' '.join(settings)}")
        return

    keyboard = get_buttons_routes(settings)
    reply_markup = InlineKeyboardMarkup(keyboard)

    update.message.reply_text('Укажите маршруты для вывода:', reply_markup=reply_markup)


def button(bot, update):
    query = update.callback_query
    logger.info(query)
    user_id = query.message.chat_id
    settings = user_settings.get(user_id, [])
    key = query.data

    if key == 'all':
        settings = list(routes_base.keys())
    elif key == 'none':
        settings = []
    elif key == 'hide':
        bot.edit_message_text(text=f"Текущие маршруты для вывода: {' '.join(settings) if settings else 'все доступные'}",
                              chat_id=query.message.chat_id,
                              message_id=query.message.message_id)
        return
    else:
        if key in settings:
            settings.remove(key)
        else:
            settings.append(key)

    user_settings[user_id] = settings
    keyboard = get_buttons_routes(settings)
    reply_markup = InlineKeyboardMarkup(keyboard)
    bot.edit_message_text(text=f"Текущие маршруты для вывода: {' '.join(settings) if settings else 'все доступные'}",
                          chat_id=query.message.chat_id,
                          message_id=query.message.message_id,
                          reply_markup=reply_markup)


def init_tg_bot():
    """Start the bot."""
    # Create the EventHandler and pass it your bot's token.
    DEBUG_TOKEN = "524433920:AAFA-Qz4-ioogQ2WRviG_mD1lRzvrz7IPUc"
    VRNBUSBOT_TOKEN = "548203169:AAE68R3o9ghnoe2LMnOkiqoU5R-OdGY4YCQ"
    updater = Updater(DEBUG_TOKEN if debug else VRNBUSBOT_TOKEN)

    # Get the dispatcher to register handlers
    dp = updater.dispatcher

    # on different commands - answer in Telegram
    updater.dispatcher.add_handler(CommandHandler('itest', itest, pass_args=True))
    updater.dispatcher.add_handler(CommandHandler('settings', itest, pass_args=True))
    updater.dispatcher.add_handler(CallbackQueryHandler(button))
    dp.add_handler(CommandHandler("start", start))

    dp.add_handler(CommandHandler("help", help))
    dp.add_handler(CommandHandler("last", last_buses, pass_args=True))
    dp.add_handler(CommandHandler("lastpro", last_buses_pro, pass_args=True))
    dp.add_handler(CommandHandler("nextbus", next_bus_handler, pass_args=True))

    dp.add_handler(CommandHandler("stats", stats))

    # on noncommand i.e message - echo the message on Telegram
    dp.add_handler(MessageHandler(Filters.text, echo))
    dp.add_handler(MessageHandler(Filters.location, location))

    # log all errors
    dp.add_error_handler(error)

    # Start the Bot
    updater.start_polling()

    # Run the bot until you press Ctrl-C or the process receives SIGINT,
    # SIGTERM or SIGABRT. This should be used most of the time, since
    # start_polling() is non-blocking and will stop the bot gracefully.
    # updater.idle()


def load_bus_routes():
    routes_base_local = {}
    r = requests.get(f'{cds_url_base}GetBuses', cookies=cookies, headers=fake_header)
    if r.text:
        result = json.loads(r.text)
        for v in result:
            if 'proj_id_' in v and 'route_name_' in v:
                route = v['route_name_']
                if route not in routes_base_local:
                    routes_base_local[v['route_name_']] = v['proj_id_']
    with open('bus_routes.json', 'wb') as f:
        json.dump(routes_base_local, codecs.getwriter('utf-8')(f), ensure_ascii=False, indent=4)
    return routes_base_local


import unittest

class TestSomeCases(unittest.TestCase):

    def test_split(self):
        input = ['104', 'Тр.', '17', '18']
        expected = ['104', 'Тр. 17', '18']
        self.assertEqual(parse_routes(input), expected)
import tornado.ioloop
import tornado.web

root = Path("./fe")
port = 8080

class NoCacheStaticFileHandler(tornado.web.StaticFileHandler):
    def set_extra_headers(self, path):
        self.set_header("Cache-control", "no-cache")

static_handler = tornado.web.StaticFileHandler if not debug else NoCacheStaticFileHandler


class BusInfoHandler(tornado.web.RequestHandler):
    def _caching(self):
        self.set_header("Cache-Control", "max-age=30")

    def bus_info_response(self, query):
        routes = sorted(parse_routes(query.split()), key=natural_sort_key)
        response = bus_request(tuple(routes))
        response = {'q': query, 'text': response}
        self.write(json.dumps(response))
        self._caching()

    def get(self):
        self.bus_info_response(self.get_argument('q'))

    def post(self):
        data = tornado.escape.json_decode(self.request.body)
        self.bus_info_response(data.get('q'))

class ArrivalHandler(tornado.web.RequestHandler):
    def _caching(self):
        self.set_header("Cache-Control", "max-age=30")

    def arrival_response(self, lat, lon):
        matches = matches_bus_stops(lat, lon)
        result = next_bus_for_matches(matches, [])
        response = {'lat': lat, 'lon': lon, 'text': result}
        self.write(json.dumps(response))
        self._caching()

    def get(self):
        (lat, lon) = (float(self.get_argument(x)) for x in ('lat', 'lon') )
        self.arrival_response(lat, lon)

    def post(self):
        data = tornado.escape.json_decode(self.request.body)
        (lat, lon) = data['lat'], data['lon']
        self.arrival_response(lat, lon)

application = tornado.web.Application([
    (r"/arrival", ArrivalHandler),
    (r"/businfo", BusInfoHandler),
    (r"/(.*)", static_handler, {"path": Path("./fe"), "default_filename": "index.html"}),
])

if __name__ == "__main__":
    init_tg_bot()
    application.listen(os.environ.get('PORT', port))
    tornado.ioloop.IOLoop.instance().start()
    # unittest.main()