"""Time-related utility functions."""

from datetime import datetime, timedelta
from typing import Tuple


def parse_time_range(time_range: str) -> Tuple[datetime, datetime]:
    """Parse time range string and return start/end datetime objects."""
    now = datetime.utcnow()
    
    if time_range.endswith('h'):
        hours = int(time_range[:-1])
        start = now - timedelta(hours=hours)
    elif time_range.endswith('m'):
        minutes = int(time_range[:-1])
        start = now - timedelta(minutes=minutes)
    elif time_range.endswith('d'):
        days = int(time_range[:-1])
        start = now - timedelta(days=days)
    elif time_range.endswith('s'):
        seconds = int(time_range[:-1])
        start = now - timedelta(seconds=seconds)
    else:
        # Default to 1 hour if format is not recognized
        start = now - timedelta(hours=1)
    
    return start, now


def format_timestamp(timestamp: datetime, format_str: str = "%Y-%m-%d %H:%M:%S UTC") -> str:
    """Format datetime object as string."""
    return timestamp.strftime(format_str)


def timestamp_to_grafana_format(timestamp: datetime) -> str:
    """Convert datetime to Grafana-compatible timestamp format."""
    return timestamp.isoformat() + 'Z'


def grafana_timestamp_to_datetime(timestamp_str: str) -> datetime:
    """Convert Grafana timestamp string to datetime object."""
    # Remove 'Z' suffix if present
    if timestamp_str.endswith('Z'):
        timestamp_str = timestamp_str[:-1]
    
    return datetime.fromisoformat(timestamp_str)