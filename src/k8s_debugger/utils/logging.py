"""Logging utilities."""

import logging.config
from typing import Dict, Any

from ..config import Settings


def setup_logging(settings: Settings) -> None:
    """Set up logging configuration."""
    logging.config.dictConfig(settings.log_config)
    
    # Set specific logger levels
    if settings.is_development:
        logging.getLogger("k8s_debugger").setLevel(logging.DEBUG)
        logging.getLogger("httpx").setLevel(logging.INFO)
        logging.getLogger("kubernetes").setLevel(logging.INFO)
    else:
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("kubernetes").setLevel(logging.WARNING)
        logging.getLogger("urllib3").setLevel(logging.WARNING)