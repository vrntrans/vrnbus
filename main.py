# #!/usr/bin/env python3.6
import logging
import os
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

import tornado.web

from cds import CdsRequest
from tgbot import BusBot
from website import BusSite

if not Path('logs').is_dir():
    Path('logs').mkdir()

# Enable logging
file_handler = TimedRotatingFileHandler("logs/vrnbus.log", 'midnight', 1)
file_handler.suffix = "%Y-%m-%d"
# noinspection SpellCheckingInspection
logging.basicConfig(format='%(asctime)s - %(levelname)s [%(filename)s:%(lineno)s %(funcName)20s] %(message)s',
                    level=logging.INFO,
                    handlers=[logging.StreamHandler(), file_handler])

logger = logging.getLogger("vrnbus")

logger.info([{k: os.environ[k]} for (k) in os.environ if 'PATH' not in k])
if 'DYNO' in os.environ:
    debug = False
else:
    debug = True

user_settings = {}

if __name__ == "__main__":
    cds = CdsRequest(logger)
    bot = BusBot(cds, user_settings, logger)
    application = BusSite(cds, logger, debug)
    application.listen(os.environ.get('PORT', 8080))
    tornado.ioloop.IOLoop.instance().start()
