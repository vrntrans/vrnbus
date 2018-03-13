from enum import Enum, auto


class TgEvent(Enum):
    START = auto()
    HELP = auto()
    LAST = auto()
    NEXT = auto()
    STATS = auto()
    LOCATION = auto()
    USER_INPUT = auto()


class WebEvent(Enum):
    ARRIVAL = auto()
    BUSINFO = auto()
    BUSSTOP = auto()


class EventTracker:
    def __init__(self, logger):
        self.logger = logger

    def tg(self, event: TgEvent, user, *params):
        user_info = f"user:{user.id}"
        self.logger.info(f"TRACK: {event} {user_info} {params if params else ''}")

    def web(self, event: WebEvent, ip, *params):
        self.logger.info(f"TRACK: {event}  {ip} {params if params else ''}")
