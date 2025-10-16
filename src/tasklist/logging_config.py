import logging
import os
import appdirs

# Define app constants for appdirs
APP_NAME = "tasklist"
APP_AUTHOR = "TaskList"


def setup_logging():
    """
    Configure logging format and level for the tasklist package.
    """
    logger = logging.getLogger("tasklist")
    logger.setLevel(logging.DEBUG)  # Root logger level for the package

    # Avoid adding multiple handlers
    if logger.hasHandlers():
        return

    # Console handler for INFO messages
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - %(message)s", "%Y-%m-%d %H:%M:%S"
    )
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # File handler for DEBUG messages
    log_dir = appdirs.user_log_dir(APP_NAME, APP_AUTHOR)
    os.makedirs(log_dir, exist_ok=True)
    log_file_path = os.path.join(log_dir, "tasklist.log")

    file_handler = logging.FileHandler(log_file_path)
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)
