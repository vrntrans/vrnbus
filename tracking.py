import datetime
from collections import defaultdict
from enum import Enum, auto


class TgEvent(Enum):
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


class WebEvent(Enum):
    ARRIVAL = auto()
    BUSINFO = auto()
    BUSMAP = auto()
    BUSSTOP = auto()


class EventTracker:
    def __init__(self, logger):
        self.logger = logger
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

    def stats(self, detailed=False):
        def replace_event_name(event):
            return str(event).replace("Event.", ".")

        events = [f'{replace_event_name(k):13} {v}' for k, v in self.events.items()]
        events.sort()
        user_stats = "\n".join(events)
        tg_count = len(self.tg_users)
        web_count = len(self.web_users)
        user_types = f"Tg users:  {tg_count}\nWeb users: {web_count}"
        stats_list = ''
        if detailed:
            stats_list = [f"{event_name}: {k} {v}"
                           for event_name, event_dict in self.detailed_events.items()
                           for k, v in event_dict.items() if v > 10]

        return f'{self.start:%Y.%m.%d %H:%M}\n{user_stats}\n{user_types} {"; ".join(stats_list)}'

    def tg(self, event: TgEvent, user, *params):
        user_info = f"user:{user.id}"
        self.add_event(event, user.id)
        self.tg_users.add(user.id)
        self.logger.info(f"TRACK: {event} {user_info} {params if params else ''}")

    def web(self, event: WebEvent, ip, *params):
        self.add_event(event, ip)
        self.web_users.add(ip)
        self.logger.info(f"TRACK: {event} ip:{ip} {params if params else ''}")
