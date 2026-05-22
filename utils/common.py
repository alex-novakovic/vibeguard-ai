from datetime import datetime
from zoneinfo import ZoneInfo

_BELGRADE = ZoneInfo("Europe/Belgrade")


def get_time() -> datetime:
    """Current Belgrade time as a timezone-aware datetime object."""
    return datetime.now(_BELGRADE)
