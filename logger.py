import logging
import os
from datetime import datetime

from config import LOG_DIR


def setup_logger(name, filename_prefix):
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    fmt = logging.Formatter(
        '%(asctime)s | %(levelname)s | %(name)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    log_file = os.path.join(
        LOG_DIR,
        f"{filename_prefix}_{datetime.now().strftime('%Y%m')}.log"
    )
    fh = logging.FileHandler(log_file, encoding='utf-8')
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    return logger
