# #!/usr/bin/env python3.6
import logging
import os

import tornado.web

from cds import CdsRequest
from tgbot import BusBot
from website import BusSite

# Enable logging
logging.basicConfig(format='%(asctime)s - %(levelname)s [%(filename)s:%(lineno)s %(funcName)20s] %(message)s',
                    level=logging.INFO)

logger = logging.getLogger(__name__)

logger.info(os.environ)
if 'DYNO' in os.environ:
    debug = False
else:
    debug = True


user_settings = {}

if __name__ == "__main__":
    import json

    print(json.__file__)
    cds = CdsRequest(logger)
    bot = BusBot(cds, user_settings, logger, debug)
    application = BusSite(cds, logger, debug)
    application.listen(os.environ.get('PORT', 8080))
    tornado.ioloop.IOLoop.instance().start()
