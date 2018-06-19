import datetime
from collections import defaultdict, deque
from typing import List

from data_types import AbuseRule


def last_time(delta: datetime.timedelta):
    return datetime.datetime.now() - delta


class AbuseChecker:
    def __init__(self, logger, rules: List[AbuseRule]):
        self.logger = logger
        self.events = {}
        self.default_rule = AbuseRule(0, 100, datetime.timedelta(minutes=60))
        self.rules = {v.event: v for v in rules}
        for rule in rules:
            self.events[rule.event] = defaultdict(lambda: deque(maxlen=rule.count))

    def reset_stats(self, user_id):
        self.events[user_id].clear()

    def prepare_dict(self, event):
        if event in self.events:
            return
        rule = self.rules.get(event)
        if rule:
            self.logger.error(f"There is no prepared dict for {event}")
            self.events[event] = defaultdict(lambda: deque(maxlen=rule.count))
            return

        self.logger.error(f"There is no rule for {event}")
        self.events[event] = defaultdict(lambda: deque(maxlen=self.default_rule.count))

    def check_time(self):
        now = datetime.datetime.now()
        return now.hour >= 20 or now.hour <= 7

    def check_user(self, event, user_id):
        if self.check_time():
            return True

        self.prepare_dict(event)
        user_events = self.events[event][user_id]
        rule = self.rules.get(event, self.default_rule)
        if len(user_events) < rule.count:
            return True

        min_time = min(user_events)
        if min_time < last_time(rule.delta):
            return True

        return False

    def add_user_event(self, event, user_id):
        self.prepare_dict(event)
        self.events[event][user_id].append(datetime.datetime.now())
        return self.check_user(event, user_id)
