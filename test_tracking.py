import logging
import unittest

from tracking import EventTracker, TgEvent, WebEvent

logging.basicConfig(format='%(asctime)s - %(levelname)s [%(filename)s:%(lineno)s %(funcName)20s] %(message)s',
                    level=logging.INFO,
                    handlers=[logging.StreamHandler()])

logger = logging.getLogger("vrnbus")
class FakeUser():
    id = 42

class TrackingTest(unittest.TestCase):
    def test_something(self):
        tracker = EventTracker(logger)
        user = FakeUser()

        tracker.tg(TgEvent.START, user)
        tracker.web(WebEvent.ARRIVAL, '')
        stats = tracker.stats()
        logger.info(stats)

        self.assertEqual(tracker.events[TgEvent.START], 1)
        self.assertEqual(tracker.events[WebEvent.ARRIVAL], 1)
        self.assertEqual(len(tracker.web_users), 1)
        self.assertEqual(len(tracker.tg_users), 1)
