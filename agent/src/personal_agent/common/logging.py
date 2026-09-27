"""Logging configuration for the Python worker."""
import logging
import sys


def configure_logging(level: str = "INFO") -> None:
    """Configure stderr logging without interfering with the JSON protocol."""
    logging.basicConfig(
        level=level,
        stream=sys.stderr,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )
    logging.getLogger().setLevel(level)
