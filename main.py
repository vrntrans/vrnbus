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
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters

def get_time(s):
    return  datetime.strptime(s, '%b %d, %Y %I:%M:%S %p')

# Enable logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)

logger = logging.getLogger(__name__)
cds_url_base = 'http://195.98.79.37:8080/CdsWebMaps/'
codd_base_usl = 'http://195.98.83.236:8080/CitizenCoddWebMaps/'
cookies = {'JSESSIONID': 'C8ED75C7EC5371CBE836BDC748BB298F', 'session_id': 'vrntrans'}
fake_header = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/63.0.3239.132 Safari/537.36'}

routes_base = {}
bus_stops = []

@cachetools.func.ttl_cache()
def get_all_buses():
    r = requests.get(f'{cds_url_base}GetBuses', cookies=cookies, headers=fake_header)
    if r.text:
        result = json.loads(r.text)
        now = datetime.now()
        hour = timedelta(hours=1)
        print(result)
        key_check = lambda x: 'name_' in x and 'last_time_' in x and (now-get_time(x['last_time_']))<hour
        short_result = [(d['name_'], d['last_time_'], d['route_name_'], d['proj_id_']) for d in result if key_check(d)]
        short_result = sorted(short_result, key=lambda x: x[2] + ' ' +str(x[3]))
        groupped = [(k, len(list(g))) for k, g in groupby(short_result, lambda x: '{}({})'.format(x[2], str(x[3])))]
        print(short_result)
        if short_result:
            buses = ' \n'.join((('{} => {}'.format(i[0], i[1])) for i in groupped))
            print(buses)
            return buses

    return 'Ничего не нашлось'


@cachetools.func.ttl_cache(ttl=60)
def bus_request(bus_route):
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
        key_check = lambda x: 'name_' in x and 'last_time_' in x and (now-get_time(x['last_time_']))<hour
        short_result = [d for d in result if key_check(d)]
        print(short_result)
        if short_result:
            stations = ' \n'.join(f"{d['route_name_']}, {get_time(d['last_time_']):%H:%M}, {d['bus_station_']}" for d in short_result)
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
    url = f'{cds_url_base}GetRouteBuses'
    if not matches:
        return f'Остановки c именем "{bus_stop}" не найдены'
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

def last_buses(bot, update, args):
    """Send a message when the command /start is issued."""
    response = bus_request(tuple(args))
    update.message.reply_text(response)

def next_bus_handler(bot, update, args):
    """Send a message when the command /start is issued."""
    response = next_bus(tuple(args))
    update.message.reply_text(response)

def get_all(bot, update, args):
    """Send a message when the command /start is issued."""
    response = get_all_buses()
    update.message.reply_text(response)


def help(bot, update, args):
    """Send a message when the command /help is issued."""
    text_caps = ' '.join(args).upper()
    update.message.reply_text("""/last номера маршрута через пробел - последние остановки
    /stats статистика
    /nextbus имя остановки - ожидаемое время прибытия""")


def echo(bot, update):
    """Echo the user message."""
    update.message.reply_text(update.message.text)


def error(bot, update, error):
    """Log Errors caused by Updates."""
    logger.warning('Update "%s" caused error "%s"', update, error)


def main():
    """Start the bot."""
    # Create the EventHandler and pass it your bot's token.
    updater = Updater("548203169:AAE68R3o9ghnoe2LMnOkiqoU5R-OdGY4YCQ")

    # Get the dispatcher to register handlers
    dp = updater.dispatcher

    # on different commands - answer in Telegram
    # dp.add_handler(CommandHandler("start", start, pass_args=True))
    dp.add_handler(CommandHandler("help", help, pass_args=True))
    dp.add_handler(CommandHandler("last", last_buses, pass_args=True))
    dp.add_handler(CommandHandler("nextbus", next_bus_handler, pass_args=True))

    dp.add_handler(CommandHandler("stats", get_all, pass_args=True))

    # on noncommand i.e message - echo the message on Telegram
    dp.add_handler(MessageHandler(Filters.text, echo))

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
    r = requests.get( f'{cds_url_base}GetBuses', cookies=cookies, headers=fake_header)
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
    main()