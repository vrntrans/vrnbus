import logging
import unittest

from abuse_checker import AbuseChecker
from tracking import EventTracker, TgEvent, WebEvent

logging.basicConfig(format='%(asctime)s - %(levelname)s [%(filename)s:%(lineno)s %(funcName)20s] %(message)s',
                    level=logging.INFO,
                    handlers=[logging.StreamHandler()])

logger = logging.getLogger("vrnbus")
class FakeUser():
    def __init__(self, id=None):
        self.id = id if id else 42

class TrackingTest(unittest.TestCase):
    def test_something(self):
        tracker = EventTracker(logger)
        user = FakeUser()

        tracker.tg(TgEvent.START, user)
        tracker.web(WebEvent.ARRIVAL, '127.0.0.1')
        stats = tracker.stats()
        detailed_stats = tracker.stats(True)
        logger.info(stats)
        logger.info(detailed_stats)

        self.assertEqual(tracker.events[TgEvent.START], 1)
        self.assertEqual(tracker.events[WebEvent.ARRIVAL], 1)
        self.assertEqual(len(tracker.web_users), 1)
        self.assertEqual(len(tracker.tg_users), 1)

    def test_detailed_stats(self):
        logger.setLevel(logging.WARNING)
        tracker = EventTracker(logger)
        user = FakeUser()

        tracker.tg(TgEvent.START, user)
        for i in range(500):
            tracker.tg(TgEvent(i%8 + 1), FakeUser(100500 + i%7))
            tracker.web(WebEvent(i%3 + 1), f'127.0.0.{i%3}')
        stats = tracker.stats()
        detailed_stats = tracker.stats(True)

        logger.setLevel(logging.INFO)
        logger.info(detailed_stats)
        self.assertNotEqual(stats, detailed_stats)


class AbuseCheckerTest(unittest.TestCase):
    def test_wo_rules(self):
        checker = AbuseChecker(logger, [])
        checker.add_user_event(WebEvent.BUSMAP, '127.0.0.1')
