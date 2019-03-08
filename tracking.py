import datetime
from collections import defaultdict
from enum import Enum, auto
from typing import List


class TgEvent(Enum):
    ABUSE = auto()
    START = auto()
    HELP = auto()
    LAST = auto()
    NEXT = auto()
    STATS = auto()
    USER_STATS = auto()
    LOCATION = auto()
    USER_INPUT = auto()
    CUSTOM_CMD = auto()
    WRONG_CMD = auto()

    @staticmethod
    def from_str(label):
        return TgEvent.__dict__.get(label)


class WebEvent(Enum):
    ABUSE = auto()
    FRAUD = auto()
    ARRIVAL = auto()
    BUSINFO = auto()
    BUSMAP = auto()
    BUSSTOP = auto()
    FULLINFO = auto()
    IPCHANGE = auto()
    IOS = auto()
    ANDROID = auto()
    USER_STATS = auto()

    @staticmethod
    def from_str(label):
        return WebEvent.__dict__.get(label)


def get_event_by_name(name: str):
    if not name or not isinstance(name, str):
        return
    if '.' in name:
        parts = name.split('.')
        if len(parts) > 2:
            return
        (event_type, event_name) = (i.upper() for i in parts)
        if event_type == 'TG':
            return TgEvent.from_str(event_name)
        if event_type == 'WEB':
            return WebEvent.from_str(event_name)

    event_name = name.upper()
    web_event = WebEvent.from_str(event_name)
    if web_event:
        return web_event
    tg_event = TgEvent.from_str(event_name)
    if tg_event:
        return tg_event


def get_events_by_names(str_events: List[str]):
    result = []
    for item in str_events:
        event_name = item.upper()
        web_event = WebEvent.get(event_name)
        if web_event:
            result.append(web_event)
        tg_event = TgEvent.get(event_name)
        if tg_event:
            result.append(tg_event)


class EventTracker:
    def __init__(self, logger, log_ignore_events: List[Enum] = None):
        self.logger = logger
        self.log_ignore_events = log_ignore_events or []
        self.events = defaultdict(int)
        self.detailed_events = defaultdict(lambda: defaultdict(int))
        self.start = datetime.datetime.now()
        self.tg_users = set()
        self.web_users = set()

    def add_event(self, event, uid):
        self.events[event] += 1
        self.detailed_events[event][uid] += 1

    def reset(self):
        self.events = defaultdict(int)
        self.start = datetime.datetime.now()
        self.tg_users = set()
        self.web_users = set()

    def stats(self, detailed=False, details_treshold=50, user_filter='', event_filter=None):
        def replace_event_name(event):
            return str(event).replace("Event.", ".")

        events = [f'{replace_event_name(event_name):13} {sum(event_dict.values())} / {len(event_dict.keys())}'
                  for event_name, event_dict in self.detailed_events.items()]
        events.sort()
        user_stats = "\n".join(events)
        tg_count = len(self.tg_users)
        web_count = len(self.web_users)
        user_types = f"Tg users:  {tg_count}\nWeb users: {web_count}"
        full_info = ''
        if detailed:
            info_list = [f"{replace_event_name(event_name)}: {k} {v}"
                         for event_name, event_dict in self.detailed_events.items()
                         for k, v in event_dict.items()
                         if v >= details_treshold
                         or (user_filter and user_filter in k)
                         or (event_filter and event_name in event_filter)
                         ]
            full_info = "\nDetails\n" + "\n".join(sorted(info_list))

        return f'{self.start:%Y.%m.%d %H:%M}\n{user_stats}\n{user_types} {full_info}'

    def tg(self, event: TgEvent, user, *params):
        user_info = f"user:{user.id}"
        self.add_event(event, str(user.id))
        self.tg_users.add(user.id)
        if event not in self.log_ignore_events:
            self.logger.info(f"TRACK: {event} {user_info} {params if params else ''}")

    def web(self, event: WebEvent, ip, *params):
        self.add_event(event, ip)
        self.web_users.add(ip)
        if event not in self.log_ignore_events:
            self.logger.info(f"TRACK: {event} ip:{ip} {params if params else ''}")
