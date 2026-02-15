import os
import logging
from dotenv import load_dotenv

load_dotenv()

DASHBOARD_PORT = int(os.getenv("DASHBOARD_PORT", 3305))
DASHBOARD_HOST = os.getenv("DASHBOARD_HOST", "127.0.0.1")
DASHBOARD_TOKEN = os.getenv("DASHBOARD_TOKEN")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
COMPOSE_FILE = os.getenv("COMPOSE_FILE", "../docker-compose.yml")
COMPOSE_PROJECT = os.getenv("COMPOSE_PROJECT_NAME", "dockerized-models")
GLOBAL_API_KEY = os.getenv("LLM_DOCK_API_KEY")

if not DASHBOARD_TOKEN:
    raise ValueError("DASHBOARD_TOKEN environment variable is required")

# Configure logging with file and console handlers
log_level = getattr(logging, LOG_LEVEL)
log_format = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")

# File handler
file_handler = logging.FileHandler("dashboard.log")
file_handler.setLevel(log_level)
file_handler.setFormatter(log_format)

# Console handler
console_handler = logging.StreamHandler()
console_handler.setLevel(log_level)
console_handler.setFormatter(log_format)

# Root logger configuration
root_logger = logging.getLogger()
root_logger.setLevel(log_level)
root_logger.addHandler(file_handler)
root_logger.addHandler(console_handler)
