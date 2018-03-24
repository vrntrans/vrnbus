import codecs
import datetime
import json
import logging
import time
from pathlib import Path

from data_providers import CdsDBDataProvider
from helpers import CustomJsonEncoder


def save_test_data(file_numbers=200, sleep_time=30):
    logging.basicConfig(format='%(asctime)s - %(levelname)s [%(filename)s:%(lineno)s %(funcName)20s] %(message)s',
                        level=logging.INFO,
                        handlers=[logging.StreamHandler()])

    logger = logging.getLogger(__name__)

    if not Path('test_data').is_dir():
        Path('test_data').mkdir()

    cds = CdsDBDataProvider(logger)
    logger.info("Start")
    for i in range(file_numbers):
        codd_data_db = cds.load_all_cds_buses()
        now = datetime.datetime.now()
        with open(f'test_data/codd_data_db{now:%y_%m_%d_%H_%M_%S}.json', 'wb') as f:
            json.dump(codd_data_db, codecs.getwriter('utf-8')(f), ensure_ascii=False, indent=1, cls=CustomJsonEncoder)
        time.sleep(sleep_time)

    logger.info("Stop")


if __name__ == '__main__':
    save_test_data()
