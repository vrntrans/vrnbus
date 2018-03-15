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
    BUSSTOP = auto()


class EventTracker:
    def __init__(self, logger):
        self.logger = logger
        self.events = defaultdict(int)
        self.start = datetime.datetime.now()

    def stats(self):
        return self.events

    def tg(self, event: TgEvent, user, *params):
        user_info = f"user:{user.id}"
        self.events[event] += 1
        self.logger.info(f"TRACK: {event} {user_info} {params if params else ''}")

    def web(self, event: WebEvent, ip, *params):
        self.events[event] += 1
        self.logger.info(f"TRACK: {event} ip:{ip} {params if params else ''}")
