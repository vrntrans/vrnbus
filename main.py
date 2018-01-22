# #!/usr/bin/env python3.6
import codecs
import json
import logging
from datetime import datetime
from datetime import timedelta
from itertools import groupby
from pathlib import Path

import cachetools.func
import requests
import telegram
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputLocationMessageContent, ReplyKeyboardRemove
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackQueryHandler


def get_time(s):
    return datetime.strptime(s, '%b %d, %Y %I:%M:%S %p')


# Enable logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)

logger = logging.getLogger(__name__)
cds_url_base = 'http://195.98.79.37:8080/CdsWebMaps/'
codd_base_usl = 'http://195.98.83.236:8080/CitizenCoddWebMaps/'
cookies = {'JSESSIONID': 'C8ED75C7EC5371CBE836BDC748BB298F', 'session_id': 'vrntrans'}
fake_header = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
                  'Chrome/63.0.3239.132 Safari/537.36'}

routes_base = {}
bus_stops = []


@cachetools.func.ttl_cache()
def get_all_buses():
    r = requests.get(f'{cds_url_base}GetBuses', cookies=cookies, headers=fake_header)
    if r.text:
        result = json.loads(r.text)
        now = datetime.now()
        hour = timedelta(hours=1)
        key_check = lambda x: 'name_' in x and 'last_time_' in x and (now - get_time(x['last_time_'])) < hour
        short_result = [(d['name_'], d['last_time_'], d['route_name_'], d['proj_id_']) for d in result if key_check(d)]
        short_result = sorted(short_result, key=lambda x: x[2] + ' ' + str(x[3]))
        groupped = [(k, len(list(g))) for k, g in groupby(short_result, lambda x: '{}({})'.format(x[2], str(x[3])))]
        print(short_result)
        if short_result:
            buses = ' \n'.join((('{} => {}'.format(i[0], i[1])) for i in groupped))
            print(buses)
            return buses

    return 'Ничего не нашлось'


@cachetools.func.ttl_cache(ttl=60)
def bus_request_as_list(bus_route):
    url = f'{cds_url_base}GetRouteBuses'
    print('bus_route', bus_route)
    if not bus_route:
        return 'Не заданы маршруты'
    routes = [{'proj_ID': routes_base.get(r.upper()), 'route': r.upper()} for r in bus_route]

    payload = {'routes': json.dumps(routes)}
    r = requests.post(url, cookies=cookies, data=payload, headers=fake_header)

    if r.text:
        result = json.loads(r.text)
        now = datetime.now()
        hour = timedelta(hours=1)
        print(result)
        key_check = lambda x: 'name_' in x and 'last_time_' in x and (now - get_time(x['last_time_'])) < hour
        short_result = [d for d in result if key_check(d)]
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
        print(stations)
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
            f"{d['route_name_']} {get_time(d['last_time_']):%H:%M} {d.get('bus_station_')} {d['name_']} " for d in short_result)
        print(stations)
        return stations

    return 'Ничего не нашлось'

@cachetools.func.ttl_cache(ttl=60)
def next_bus_for_lat_lon(lat, lon):
    url = f'{codd_base_usl}GetNextBus'
    payload = {'lat': lat, 'lon': lon}
    r = requests.post(url, data=payload, headers=fake_header)
    if r.text:
        result = json.loads(r.text)
        return result


@cachetools.func.ttl_cache(ttl=60)
def next_bus(bus_stop):
    bus_stop = ' '.join(bus_stop)
    matches = [x for x in bus_stops if bus_stop.upper() in x['NAME_'].upper()]
    print(bus_stop, matches)
    if not matches:
        return f'Остановки c именем "{bus_stop}" не найдены'
    if len(matches) > 5:
        stops_matches = '\n'.join([x['NAME_'] for x in matches[:20]])
        return f'Уточните остановку. Найденные варианты:\n{stops_matches}'
    result = []
    for item in matches:
        arrivals = next_bus_for_lat_lon(item['LAT_'], item['LON_'])
        if arrivals:
            header = arrivals[0]
            items = [x for x in arrivals[1:] if x['time_'] > 0]
            if not items:
                result.append(f'Остановка {header["rname_"]}: нет данных')
                continue
            next_bus_info = f"Остановка {header['rname_']}:\n"
            next_bus_info += '\n'.join((f"{x['rname_']} - {x['time_']} мин" for x in items))
            result.append(next_bus_info)
    print('\n'.join(result))
    return '\n'.join(result)

# @cachetools.func.ttl_cache(ttl=60)
def next_bus_for_matches(bus_matches):
    result = []
    for item in bus_matches:
        arrivals = next_bus_for_lat_lon(item['LAT_'], item['LON_'])
        if arrivals:
            header = arrivals[0]
            items = [x for x in arrivals[1:] if x['time_'] > 0]
            if not items:
                result.append(f'Остановка {header["rname_"]}: нет данных')
                continue
            next_bus_info = f"Остановка {header['rname_']}:\n"
            next_bus_info += '\n'.join((f"{x['rname_']} - {x['time_']} мин" for x in items))
            result.append(next_bus_info)
    print('\n'.join(result))
    return '\n'.join(result)

def last_buses(bot, update, args):
    """Send a message when the command /start is issued."""
    response = bus_request(tuple(args))
    update.message.reply_text(response)


def last_buses_pro(bot, update, args):
    """Send a message when the command /start is issued."""
    response = bus_request_pro(tuple(args))
    update.message.reply_text(response)

def next_bus_handler(bot, update, args):
    """Send a message when the command /start is issued."""
    if not args:
        update.message.reply_text("empty")
        location_btn = telegram.KeyboardButton(text="Местоположение", request_location=True)
        cancel_btn = telegram.KeyboardButton(text="Отмена")
        custom_keyboard = [[location_btn, cancel_btn]]
        reply_markup = telegram.ReplyKeyboardMarkup(custom_keyboard, one_time_keyboard=True)
        update.message.reply_text("""Не указана остановка, попробуйте указать местоположение""", reply_markup=reply_markup)
        return

    response = next_bus(tuple(args))
    update.message.reply_text(response)


def stats(bot, update, args):
    """Send a message when the command /stats is issued."""
    response = get_all_buses()
    update.message.reply_text(response)


def help(bot, update):
    """Send a message when the command /help is issued."""
    update.message.reply_text("""/last номера маршрутов через пробел - последние остановки
/nextbus имя остановки - ожидаемое время прибытия""", reply_markup=ReplyKeyboardRemove())

def start(bot, update):
    """Send a message when the command /help is issued."""
    location_keyboard = telegram.KeyboardButton(text="Местоположение", request_location=True)
    cancel_button = telegram.KeyboardButton(text="Отмена")
    custom_keyboard = [[location_keyboard, cancel_button ]]
    reply_markup = telegram.ReplyKeyboardMarkup(custom_keyboard, one_time_keyboard=True)
    update.message.reply_text( """/last номера маршрутов через пробел - последние остановки
/nextbus имя остановки - ожидаемое время прибытия zzzz""", reply_markup = reply_markup)

def echo(bot, update):
    """Echo the user message."""
    if update.message.text == 'Отмена':
        update.message.reply_text(update.message.text, reply_markup=ReplyKeyboardRemove())


def error(bot, update, error):
    """Log Errors caused by Updates."""
    logger.warning('Update "%s" caused error "%s"', update, error)

def location(bot, update):
    user = update.message.from_user
    user_location = update.message.location
    logger.info("Location of %s: %f / %f", user.first_name, user_location.latitude,
                user_location.longitude)
    (lat, lon) =  user_location.latitude, user_location.longitude
    distance = lambda item: pow(pow(item['LON_'] - lat, 2) + pow(item['LAT_'] - lon, 2), 0.5)

    matches = sorted(bus_stops, key=distance)[:3]

    logger.info(matches)
    result = next_bus_for_matches(matches)

    update.message.reply_text(result, reply_markup=ReplyKeyboardRemove())

def init_tg_bot():
    """Start the bot."""
    # Create the EventHandler and pass it your bot's token.
    updater = Updater("548203169:AAE68R3o9ghnoe2LMnOkiqoU5R-OdGY4YCQ")

    # Get the dispatcher to register handlers
    dp = updater.dispatcher

    # on different commands - answer in Telegram
    dp.add_handler(CommandHandler("start", start))

    dp.add_handler(CommandHandler("help", help))
    dp.add_handler(CommandHandler("last", last_buses, pass_args=True))
    dp.add_handler(CommandHandler("lastpro", last_buses_pro, pass_args=True))
    dp.add_handler(CommandHandler("nextbus", next_bus_handler, pass_args=True))

    dp.add_handler(CommandHandler("stats", stats, pass_args=True))

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
    updater.idle()


def load_bus_routes():
    global routes_base
    r = requests.get(f'{cds_url_base}GetBuses', cookies=cookies, headers=fake_header)
    if r.text:
        result = json.loads(r.text)
        for v in result:
            if 'proj_id_' in v and 'route_name_' in v:
                route = v['route_name_']
                if route not in routes_base:
                    routes_base[v['route_name_']] = v['proj_id_']
    with open('bus_routes.json', 'wb') as f:
        json.dump(routes_base, codecs.getwriter('utf-8')(f), ensure_ascii=False, indent=4)


def init_routes():
    global routes_base
    my_file = Path("bus_routes.json")
    if my_file.is_file():
        with open(my_file, 'rb') as f:
            routes_base = json.load(f)
    else:
        load_bus_routes()

    print('finished init_routes')


def init_bus_stops():
    global bus_stops
    with open('bus_stops.json', 'rb') as f:
        bus_stops = json.load(f)
    print('finished init_bus_stops')

if __name__ == "__main__":
    init_routes()
    init_bus_stops()
    init_tg_bot()
