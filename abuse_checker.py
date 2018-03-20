import datetime
from collections import defaultdict, deque
from typing import List

from data_types import AbuseRule


def last_time(delta:datetime.timedelta):
    return datetime.datetime.now() - delta

class AbuseChecker:
    def __init__(self, logger, rules: List[AbuseRule]):
        self.logger = logger
        self.events = defaultdict(lambda: defaultdict(lambda: deque(maxlen=10)))
        self.rules = {v.event: v for v in rules}
        for rule in rules:
            self.events[rule.event] = defaultdict(lambda: deque(maxlen=rule.count))

    def reset_stats(self, user_id):
        self.events[user_id].clear()

    def check_user(self, event, user_id):
        user_events = self.events[event][user_id]
        if len(user_events) < 10:
            return True

        min_time = min(user_events)
        if min_time < last_time(self.rules[event].delta):
            return True

        return False

    def add_user_event(self, event, user_id):
        self.events[event][user_id].append(datetime.datetime.now())
        return self.check_user(event, user_id)
