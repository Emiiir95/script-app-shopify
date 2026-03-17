import logging
import os

LOG_FILE = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "logs", "app.log"))
os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
    ],
)

_logger = logging.getLogger("shopify_app")


def log(msg, level="info", also_print=False):
    getattr(_logger, level)(msg)
    if also_print:
        prefix = {"info": "[INFO]", "warning": "[WARN]", "error": "[ERREUR]"}.get(level, "[LOG]")
        print(f"{prefix} {msg}")
