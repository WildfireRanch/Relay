# services/logger.py

import logging
from datetime import datetime

# Basic logging config
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

def log_info(message: str):
    logging.info(message)

def log_warning(message: str):
    logging.warning(message)

def log_error(message: str):
    logging.error(message)

def log_event(event: str, data: dict = {}):
    timestamp = datetime.utcnow().isoformat()
    logging.info(f"{timestamp} - EVENT: {event} | DATA: {data}")
