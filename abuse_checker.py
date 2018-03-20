import datetime
from collections import defaultdict, deque


def last_time():
    return datetime.datetime.now() - datetime.timedelta(minutes=60)


class AbuseChecker:
    def __init__(self, logger):
        self.logger = logger
        self.events = defaultdict(lambda: deque(maxlen=10))

    def check_user(self, user_id):
        user_events = self.events[user_id]
        if len(user_events) < 10:
            return True

        min_time = min(user_events)
        if min_time < last_time():
            return True

        return False

    def add_user_event(self, user_id):
        self.events[user_id].append(datetime.datetime.now())
        return self.check_user(user_id)
