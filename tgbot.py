import os
import re
import textwrap

import cachetools
from telegram import ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup, \
    KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import CommandHandler, CallbackQueryHandler, Filters, MessageHandler, Updater, run_async
from tornado.httpclient import AsyncHTTPClient

from data_types import UserLoc, ArrivalInfo
from helpers import parse_routes, natural_sort_key, grouper, SearchResult, parse_int
from tracking import EventTracker, TgEvent

try:
    import settings

    VRNBUSBOT_TOKEN = settings.VRNBUSBOT_TOKEN
    PING_HOST = settings.PING_HOST
except ImportError:
    env = os.environ
    VRNBUSBOT_TOKEN = env.get('VRNBUSBOT_TOKEN')
    PING_HOST = env.get('PING_HOST', 'http://localhost:8080')


class BusBot:
    def __init__(self, cds, user_settings, logger, tracker:EventTracker):
        """Start the bot."""
        self.cds = cds
        self.user_settings = user_settings
        self.logger = logger
        self.tracker = tracker
        # Create the EventHandler and pass it your bot's token.
        if not VRNBUSBOT_TOKEN:
            self.logger.error("The Telegram bot token is empty. Use @BotFather to get your token")
            return
        self.updater = Updater(VRNBUSBOT_TOKEN, request_kwargs={'read_timeout':10})

        # Get the dispatcher to register handlers
        self.dp = self.updater.dispatcher

        # on different commands - answer in Telegram
        self.updater.dispatcher.add_handler(CommandHandler('settings', self.settings, pass_args=True))
        self.updater.dispatcher.add_handler(CallbackQueryHandler(self.settings_button))
        self.dp.add_handler(CommandHandler("start", self.start))

        self.dp.add_handler(CommandHandler("help", self.helpcmd))
        self.dp.add_handler(CommandHandler("last", self.last_buses, pass_args=True))

        self.dp.add_handler(CommandHandler("nextbus", self.next_bus_handler, pass_args=True))

        self.dp.add_handler(CommandHandler("userstats", self.user_stats))
        self.dp.add_handler(CommandHandler("userstatspro", self.user_stats_pro, pass_args=True))

        self.dp.add_handler(CommandHandler("stats", self.stats))
        self.dp.add_handler(CommandHandler("statspro", self.stats_full))
        #
        # # on noncommand i.e message - echo the message on Telegram

        self.dp.add_handler(MessageHandler(Filters.command, self.custom_command))
        self.dp.add_handler(MessageHandler(Filters.text, self.user_input))
        self.dp.add_handler(MessageHandler(Filters.location, self.location))
        #
        # # log all errors
        self.dp.add_error_handler(self.error)

        # Start the Bot
        self.updater.start_polling(timeout=30)

        # Run the bot until you press Ctrl-C or the process receives SIGINT,
        # SIGTERM or SIGABRT. This should be used most of the time, since
        # start_polling() is non-blocking and will stop the bot gracefully.
        # updater.idle()

    def track(self, event:TgEvent, update, *params):
        user = update.message.from_user
        self.tracker.tg(event, user, *params)

    @run_async
    def custom_command(self, bot, update):
        command = update.message.text
        if command.startswith('/nextbus_'):
            match = re.match(r'/nextbus_(\d*)[ ]*(.*)', command)
            if match and match.group(1):
                id = int(match.group(1))
                bus_stop = self.cds.get_bus_stop_from_id(id)
                if bus_stop:
                    self.track(TgEvent.CUSTOM_CMD, update, command)
                    self.next_bus_for_bus_stop(update, bus_stop, match.group(2))
                    return

        self.track(TgEvent.WRONG_CMD, update, command, "Didn't find")
        bot.send_message(chat_id=update.message.chat_id,
                         text=f"Sorry, I didn't understand that command. {update.message.text}")

    def error(self, _, update, error):
        """Log Errors caused by Updates."""
        self.logger.warning('Update "%s" caused error "%s"', update, error)
        if update:
            update.message.reply_text(f"Update caused error {error}")

    @run_async
    def start(self, _, update):
        self.ping_prod()
        self.track(TgEvent.START, update)

        location_keyboard = KeyboardButton(text="Местоположение", request_location=True)
        cancel_button = KeyboardButton(text="Отмена")
        custom_keyboard = [[location_keyboard, cancel_button]]
        reply_markup = ReplyKeyboardMarkup(custom_keyboard, one_time_keyboard=True)
        update.message.reply_text(
            "/nextbus имя остановки - ожидаемое время прибытия\n"
            "Отправка местоположения - ожидаемое время прибытия для ближайших "
            "трёх остановок\n"
            "/last номера маршрутов через пробел - последние "
            "остановки автобусов\n"
            "Свободный ввод - номера маршрутов и расстояние до автобусов "
            "(если отправляли местоположение)",
            reply_markup=reply_markup)

    @run_async
    def helpcmd(self, _, update):
        """Send a message when the command /help is issued."""
        self.ping_prod()
        user = update.message.from_user
        self.track(TgEvent.HELP, update)
        update.message.reply_text("""
/nextbus имя остановки - ожидаемое время прибытия

/stats - короткая статистика по автобусам онлайн

/last номера маршрутов через пробел - последние остановки

/settings [+|-|add|del|all|none|все] номера маршрутов - фильтрация по маршрутам

Отправка местоположения - ожидаемое время прибытия для ближайших трёх остановок
Свободный ввод - номера маршрутов и расстояние до автобусов (если отправляли местоположение)

Примеры:
/nextbus памятник славы - выведет прибытие на остановки:
    Памятник Славы (Московский проспект в центр),
    Памятник славы (Московский проспект из центра),
    Памятник славы (ул. Хользунова в центр)

/last 5а 113кш - выведет последние остановки автобусов на маршрутах 5А и 113КШ

/settings 27 5а - фильтрует автобусы в остальных командах, оставляя только выбранные
/settings all - выбрать все (эквивалентно /settings none) или
/settings все

/settings add 104 125 - добавить к фильтру маршруты 104 125 или
/settings + 104 125

/settings del 37 52 - удалить из фильтра маршруты 37 52 или
/settings - 37 52
""",
                                  reply_markup=ReplyKeyboardRemove())

    def send_text(self, text, update):
        for part in textwrap.wrap(text, 4000, replace_whitespace=False):
            update.message.reply_text(part)

    @run_async
    def last_buses(self, _, update, args):
        """Send a message when the command /last is issued."""
        self.ping_prod()
        user = update.message.from_user

        self.track(TgEvent.LAST, update, args)
        user_loc = self.user_settings.get(user.id, {}).get('user_loc', None)
        response = self.cds.bus_request(parse_routes(args), user_loc=user_loc)
        text = response[0]
        self.track(TgEvent.LAST, update, args)
        self.logger.debug(f"last_buses. User: {user}; Response {' '.join(text.split())}")
        self.send_text(text, update)

    def get_buttons_routes(self, user_routes):
        # TODO: too many buttons
        routes_list = sorted(list(self.cds.bus_routes.keys()), key=natural_sort_key)
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

    @run_async
    def settings(self, _, update, args):
        user_id = update.message.from_user.id
        settings = self.user_settings.get(user_id, {})
        route_settings = settings.get('route_settings', [])
        input_routes = parse_routes(args)[1]
        if input_routes:
            cmd = input_routes[0].lower()
            change_routes = [y for x in input_routes
                             for y in self.cds.bus_routes.keys() if x.upper() == y.upper()]
            if len(input_routes) == 1 and cmd in ('all', 'none', 'все'):
                route_settings = []
            elif cmd in ('del', '-'):
                route_settings = [x for x in route_settings if x not in change_routes]
            elif cmd in ('add', '+'):
                route_settings = list(set(route_settings + change_routes))
            else:
                route_settings = change_routes
            settings['route_settings'] = sorted(route_settings, key=natural_sort_key)
            self.user_settings[user_id] = settings
            update.message.reply_text(f"Текущие маршруты для вывода: {' '.join(route_settings)}")
            return

        keyboard = self.get_buttons_routes(route_settings)
        reply_markup = InlineKeyboardMarkup(keyboard)

        update.message.reply_text('Укажите маршруты для вывода:', reply_markup=reply_markup)

    @run_async
    def settings_button(self, bot, update):
        query = update.callback_query
        self.logger.info(query)
        user_id = query.message.chat_id
        user_settings = self.user_settings.get(user_id, {})
        settings = user_settings.get('route_settings', [])
        key = query.data

        if key == 'all':
            settings = list(self.cds.bus_routes.keys())
        elif key == 'none':
            settings = []
        elif key == 'hide':
            routes = ' '.join(settings) if settings else 'все доступные'
            bot.edit_message_text(text=f"Текущие маршруты для вывода: {routes}",
                                  chat_id=query.message.chat_id,
                                  message_id=query.message.message_id)
            return
        else:
            if key in settings:
                settings.remove(key)
            else:
                settings.append(key)

        user_settings['route_settings'] = settings
        self.user_settings[user_id] = user_settings
        keyboard = self.get_buttons_routes(settings)
        reply_markup = InlineKeyboardMarkup(keyboard)
        routes = ' '.join(settings) if settings else 'все доступные'
        bot.edit_message_text(text=f"Текущие маршруты для вывода: {routes}",
                              chat_id=query.message.chat_id,
                              message_id=query.message.message_id,
                              reply_markup=reply_markup)

    def get_text_from_arrival_info(self, arrival_info: ArrivalInfo):
        def text_for_bus_stop(key, value):
            s = (f'```{value}```' if value else '')
            command = f'/nextbus_{self.cds.get_bus_stop_id(key)}'
            return f"[{command}]({command}) {key}\n{s} "

        next_bus_text = '\n'.join([text_for_bus_stop(k, v) for (k, v) in arrival_info.bus_stops.items()])
        return f'{arrival_info.header}\n{next_bus_text}'

    @run_async
    def next_bus_general(self, update, args):
        user = update.message.from_user

        self.track(TgEvent.NEXT, update, args)
        if not args:
            location_btn = KeyboardButton(text="Местоположение", request_location=True)
            cancel_btn = KeyboardButton(text="Отмена")
            custom_keyboard = [[location_btn, cancel_btn]]
            reply_markup = ReplyKeyboardMarkup(custom_keyboard, one_time_keyboard=True)
            update.message.reply_text("""Не указана остановка, попробуйте указать местоположение""",
                                      reply_markup=reply_markup)
            return

        user_settings = self.user_settings.get(user.id, {})
        search_result = SearchResult(bus_routes=tuple(user_settings.get('route_settings', [])))
        bus_stop_name = args if isinstance(args, str) else ' '.join(args)
        response = self.cds.next_bus(bus_stop_name, search_result)
        update.message.reply_text(self.get_text_from_arrival_info(response), parse_mode='Markdown')

    def next_bus_for_bus_stop(self, update, bus_stop, params):
        user = update.message.from_user

        search_params = parse_routes(params)

        self.track(TgEvent.NEXT, update, bus_stop, params)

        response = self.cds.next_bus_for_matches((bus_stop, ), search_params)
        update.message.reply_text(self.get_text_from_arrival_info(response), parse_mode='Markdown')

    def next_bus_handler(self, _, update, args):
        self.next_bus_general(update, args)

    @run_async
    def send_stats(self, update, full_info):
        self.ping_prod()
        user = update.message.from_user

        self.track(TgEvent.STATS, update, full_info)
        response = self.cds.get_bus_statistics(full_info)
        update.message.reply_text(f'```\n{response}\n```', parse_mode='Markdown')

    def stats(self, _, update):
        """Send a message when the command /stats is issued."""
        self.send_stats(update, False)

    def stats_full(self, _, update):
        """Send a message when the command /stats is issued."""
        self.send_stats(update, True)

    @run_async
    def user_stats(self, _, update):
        self.ping_prod()
        self.track(TgEvent.USER_STATS, update)
        stats = self.tracker.stats()
        self.logger.debug(stats)
        update.message.reply_text(f'```\n{stats}\n```',
                                  parse_mode='Markdown')

    @run_async
    def user_stats_pro(self, _, update, args):
        # TODO: Add user checking as a module (white/black lists and so on)
        if update.message.from_user.id != 26943105:
            self.logger.error(f"Unknown user {update.message.from_user}")
            return
        self.ping_prod()
        self.track(TgEvent.USER_STATS, update)
        threshold, valid_threshold = parse_int(args[:1], 50)
        user_filter = ''.join(args if not valid_threshold else args[1:])
        # event_filter =
        stats = self.tracker.stats(True, threshold, user_filter)
        self.logger.debug(stats)
        update.message.reply_text(f'```\n{stats}\n```',
                                  parse_mode='Markdown')

    @run_async
    def user_input(self, bot, update):
        self.ping_prod()
        message = update.message
        user = message.from_user
        text = message.text
        l_text = text.lower()

        self.track(TgEvent.USER_INPUT, update, text[:30])
        if not text or text == 'Отмена':
            message.reply_text(text=f"Попробуйте воспользоваться справкой /help",
                               reply_markup=ReplyKeyboardRemove())
            return

        if l_text == 'на рефакторинг!':
            message.reply_text('Тогда срочно сюда @deeprefactoring!')
            return


        if l_text.startswith("ост") or l_text.startswith("аст"):
            args = text.lower().split(' ')[1:]
            self.next_bus_general(update, args)
            return

        match = re.search('https://maps\.google\.com/maps\?.*&ll=(?P<lat>[-?\d.]*),(?P<lon>[-?\d.]*)', text)
        if match:
            (lat, lon) = (match.group('lat'), match.group('lon'))
            self.show_arrival(update, float(lat), float(lon))
        else:
            user_loc = self.user_settings.get(user.id, {}).get('user_loc', None)
            self.logger.info(f"User: {user} '{text}' {user_loc}")
            response = self.cds.bus_request(parse_routes(text), user_loc=user_loc)
            self.logger.debug(f'"{text}" User: {user}; Response: {response[:5]} from {len(response)}')
            reply_text = response[0]
            for part in textwrap.wrap(reply_text, 4000, replace_whitespace=False):
                update.message.reply_text(part, reply_markup=ReplyKeyboardRemove())

    def show_arrival(self, update, lat, lon):
        user = update.message.from_user

        self.track(TgEvent.NEXT, update, lat, lon)
        self.logger.info(f"User: {user} {lat}, {lon}")
        matches = self.cds.matches_bus_stops(lat, lon)
        user_loc = UserLoc(lat, lon)
        settings = self.user_settings.get(user.id, {})
        settings['user_loc'] = user_loc
        self.user_settings[user.id] = settings
        bus_routes = settings.get('route_settings')
        search_result = SearchResult(bus_routes=(bus_routes if bus_routes else tuple()))
        arrival_info = self.cds.next_bus_for_matches(tuple(matches), search_result)
        self.logger.debug(f"next_bus_for_matches {user} {arrival_info}")
        update.message.reply_text(self.get_text_from_arrival_info(arrival_info), parse_mode='Markdown',
                                  reply_markup=ReplyKeyboardRemove())

    @run_async
    def location(self, _, update):
        self.ping_prod()
        loc = update.message.location
        (lat, lon) = loc.latitude, loc.longitude
        self.show_arrival(update, lat, lon)

    @cachetools.func.ttl_cache(ttl=30)
    def ping_prod(self):
        http_client = AsyncHTTPClient()
        http_client.fetch(f"{PING_HOST}/ping")
