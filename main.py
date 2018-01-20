# #!/usr/bin/env python3.6
import json
from datetime import datetime
from pathlib import Path

import tornado.ioloop
import tornado.web
import requests
import json
import telegram
import cachetools
import cachetools.func
import tornado.ioloop
import tornado.web

class MainHandler(tornado.web.RequestHandler):
    def get(self):
        self.write("Hello, world")

def make_app():
    return tornado.web.Application([
        (r"/", MainHandler),
    ])

from telegram.ext import Updater, CommandHandler, MessageHandler, Filters
import logging
from datetime import datetime
from datetime import timedelta
from itertools import groupby

datetime_object = datetime.strptime('Jun 1 2005  1:33PM', '%b %d %Y %I:%M%p')

def get_time(s):
    return  datetime.strptime(s, '%b %d, %Y %I:%M:%S %p')

# Enable logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)

logger = logging.getLogger(__name__)
cds_url_base = 'http://195.98.79.37:8080/CdsWebMaps/'
codd_base_usl = 'http://195.98.83.236:8080/CitizenCoddWebMaps/'
cookies = {'JSESSIONID': 'C8ED75C7EC5371CBE836BDC748BB298F', 'session_id': 'vrntrans'}

routes_base = {}

@cachetools.func.ttl_cache()
def get_all_buses():
    r = requests.get(f'{cds_url_base}GetBuses', cookies=cookies)
    if r.text:
        result = json.loads(r.text)
        now = datetime_object.now()
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
    routes = [{'proj_ID': routes_base.get(r), 'route': r} for r in bus_route]

    payload = {'routes': json.dumps(routes)}
    r = requests.post(url, cookies=cookies, data=payload)

    if r.text:
        result = json.loads(r.text)
        now = datetime_object.now()
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


def last_buses(bot, update, args):
    """Send a message when the command /start is issued."""
    response = bus_request(tuple(args))
    update.message.reply_text(response)

def get_all(bot, update, args):
    """Send a message when the command /start is issued."""
    response = get_all_buses()
    update.message.reply_text(response)


def help(bot, update, args):
    """Send a message when the command /help is issued."""
    text_caps = ' '.join(args).upper()
    update.message.reply_text('/last номера маршрута через пробел - последние остановки\n/stats статистика')


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
    # updater.idle()

def init_dictionary():
    global routes_base
    r = requests.get( f'{cds_url_base}GetBuses', cookies=cookies)
    if r.text:
        result = json.loads(r.text)
        for v in result:
            if 'proj_id_' in v and 'route_name_' in v:
                route = v['route_name_']
                if route not in routes_base:
                    routes_base[v['route_name_']] = v['proj_id_']

if __name__ == "__main__":
    init_dictionary()
    app = make_app()
    app.listen(8080)
    main()
    tornado.ioloop.IOLoop.current().start()