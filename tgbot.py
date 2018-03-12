import os
import re

import cachetools
from numpy.ma import isin
from telegram import ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup, \
    KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import CommandHandler, CallbackQueryHandler, Filters, MessageHandler, Updater
from tornado.httpclient import AsyncHTTPClient

from data_types import UserLoc
from helpers import parse_routes, natural_sort_key, grouper, SearchResult

try:
    import settings

    VRNBUSBOT_TOKEN = settings.VRNBUSBOT_TOKEN
    PING_HOST = settings.PING_HOST
except ImportError:
    env = os.environ
    VRNBUSBOT_TOKEN = env['VRNBUSBOT_TOKEN']
    PING_HOST = env['PING_HOST']


class BusBot:
    def __init__(self, cds, user_settings, logger):
        """Start the bot."""
        self.cds = cds
        self.user_settings = user_settings
        self.logger = logger
        # Create the EventHandler and pass it your bot's token.
        self.updater = Updater(VRNBUSBOT_TOKEN)

        # Get the dispatcher to register handlers
        self.dp = self.updater.dispatcher

        # on different commands - answer in Telegram
        self.updater.dispatcher.add_handler(CommandHandler('settings', self.settings, pass_args=True))
        self.updater.dispatcher.add_handler(CallbackQueryHandler(self.settings_button))
        self.dp.add_handler(CommandHandler("start", self.start))

        self.dp.add_handler(CommandHandler("help", self.helpcmd))
        self.dp.add_handler(CommandHandler("last", self.last_buses, pass_args=True))

        self.dp.add_handler(CommandHandler("nextbus", self.next_bus_handler, pass_args=True))

        self.dp.add_handler(CommandHandler("stats", self.stats))
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

    def custom_command(self, bot, update):
        command = update.message.text
        if command.startswith('/nextbus_'):
            match = re.match(r'/nextbus_(\d*)$', command)
            if match and match.group(1):
                id = int(match.group(1))
                bus_stop = self.cds.get_bus_stop_from_id(id)
                if bus_stop:
                    self.next_bus_general(update, bus_stop.NAME_)
                    return
        bot.send_message(chat_id=update.message.chat_id, text=f"Sorry, I didn't understand that command. {update.message.text}")

    def error(self, _, update, error):
        """Log Errors caused by Updates."""
        self.logger.warning('Update "%s" caused error "%s"', update, error)
        if update:
            update.message.reply_text(f"Update caused error {error}")

    def start(self, _, update):
        """Send a message when the command /help is issued."""
        self.ping_prod()
        user = update.message.from_user
        self.logger.info(f"start. User: {user};")

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

    def helpcmd(self, _, update):
        """Send a message when the command /help is issued."""
        self.ping_prod()
        user = update.message.from_user
        self.logger.info(user)
        update.message.reply_text("""
/nextbus имя остановки - ожидаемое время прибытия

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

    def last_buses(self, _, update, args):
        """Send a message when the command /last is issued."""
        self.ping_prod()
        user = update.message.from_user
        self.logger.info(f"last_buses. User: {user}; {args}")
        user_loc = self.user_settings.get(user.id, {}).get('user_loc', None)
        response = self.cds.bus_request(parse_routes(args), user_loc=user_loc)
        text = response[0]
        self.logger.info(f"last_buses. User: {user}; Response {' '.join(text.split())}")
        update.message.reply_text(text)

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

    def next_bus_general(self, update, args):
        def text_for_bus_stop(key, value):
            s = (f'```{value}```' if value else '')
            command = f'/nextbus_{self.cds.get_bus_stop_id(key)}'
            return f"[{command}]({command}) {key}\n{s} "

        user = update.message.from_user
        self.logger.info(f"next_bus_handler. User: {user}; {args}")
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
        next_bus_text = '\n'.join([text_for_bus_stop(k, v) for (k, v) in response.bus_stops.items()])
        update.message.reply_text(f'{response.header}\n{next_bus_text}', parse_mode='Markdown')

    def next_bus_handler(self, _, update, args):
        self.next_bus_general(update, args)

    def stats(self, _, update):
        """Send a message when the command /stats is issued."""
        self.ping_prod()
        user = update.message.from_user
        self.logger.info(f"Stats. User: {user}")
        response = self.cds.get_bus_statistics()
        update.message.reply_text(f'```\n{response}\n```', parse_mode='Markdown')

    def user_input(self, bot, update):
        self.ping_prod()
        message = update.message
        user = message.from_user
        text = message.text

        self.logger.info(f'" User: {user}; {text[:30]}"')

        if not text or text == 'Отмена':
            message.reply_text(text=f"Попробуйте воспользоваться справкой /help",
                               reply_markup=ReplyKeyboardRemove())
            return

        if text.lower() == 'на рефакторинг!':
            message.reply_text('Тогда срочно сюда @deeprefactoring!')
            return

        match = re.search('https://maps\.google\.com/maps\?.*&ll=(?P<lat>[-?\d.]*),(?P<lon>[-?\d.]*)', text)
        if match:
            (lat, lon) = (match.group('lat'), match.group('lon'))
            self.show_arrival(update, float(lat), float(lon))
        else:
            user_loc = self.user_settings.get(user.id, {}).get('user_loc', None)
            self.logger.info(f"{user} '{text}' {user_loc}")
            response = self.cds.bus_request(parse_routes(text), user_loc=user_loc)
            self.logger.debug(f'"{text}" User: {user}; Response: {response[:5]} from {len(response)}')
            reply_text = response[0]
            if len(reply_text) > 4000:
                message.reply_text("Слишком длинный запрос, показаны первые 4000 символов:\n" +
                                   response[0][:4000],
                                   reply_markup=ReplyKeyboardRemove())
            else:
                message.reply_text(reply_text, reply_markup=ReplyKeyboardRemove())

    def show_arrival(self, update, lat, lon):
        user = update.message.from_user
        self.logger.info("Location of %s: %f / %f", user.first_name, lat, lon)
        matches = self.cds.matches_bus_stops(lat, lon)
        user_loc = UserLoc(lat, lon)
        settings = self.user_settings.get(user.id, {})
        settings['user_loc'] = user_loc
        self.user_settings[user.id] = settings
        bus_routes = settings.get('route_settings')
        search_result = SearchResult(bus_routes=(bus_routes if bus_routes else tuple()))
        result = self.cds.next_bus_for_matches(tuple(matches), search_result)
        self.logger.debug(f"next_bus_for_matches {user} {result}")
        update.message.reply_text(f'```\n{result[0]}\n```',
                                  reply_markup=ReplyKeyboardRemove(),
                                  parse_mode='Markdown')

    def location(self, _, update):
        self.ping_prod()
        loc = update.message.location
        (lat, lon) = loc.latitude, loc.longitude
        self.show_arrival(update, lat, lon)

    @cachetools.func.ttl_cache(ttl=30)
    def ping_prod(self):
        http_client = AsyncHTTPClient()
        http_client.fetch(f"{PING_HOST}/ping")
