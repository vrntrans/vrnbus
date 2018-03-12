# #!/usr/bin/env python3.6
import logging
import os
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

import tornado.web

from cds import CdsRequest
from data_providers import CdsTestDataProvider, CdsDBDataProvider
from tgbot import BusBot
from website import BusSite

if not Path('logs').is_dir():
    Path('logs').mkdir()

# Enable logging
file_handler = TimedRotatingFileHandler("logs/vrnbus.log", 'midnight', 1)
file_handler.suffix = "%Y-%m-%d"
# noinspection SpellCheckingInspection
logging.basicConfig(format='%(asctime)s.%(msecs)03d - %(levelname)s [%(filename)s:%(lineno)s %(funcName)10s] %(message)s',
                    datefmt="%H:%M:%S",
                    level=logging.INFO,
                    handlers=[logging.StreamHandler(), file_handler])

logger = logging.getLogger("vrnbus")

logger.info([{k: os.environ[k]} for (k) in os.environ if 'PATH' not in k])

LOAD_TEST_DATA = False

try:
    import settings
    LOAD_TEST_DATA = settings.LOAD_TEST_DATA
except ImportError:
    settings = None

user_settings = {}

if __name__ == "__main__":
    data_provider = CdsTestDataProvider(logger) if LOAD_TEST_DATA else CdsDBDataProvider(logger)
    cds = CdsRequest(logger, data_provider)
    bot = BusBot(cds, user_settings, logger)
    application = BusSite(cds, logger)
    application.listen(os.environ.get('PORT', 8080))
    tornado.ioloop.IOLoop.instance().start()
