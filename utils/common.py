from datetime import datetime
from zoneinfo import ZoneInfo

_BELGRADE = ZoneInfo("Europe/Belgrade")


def now() -> str:
    """Current Belgrade time as ISO 8601 string, trimmed to seconds."""
    return datetime.now(_BELGRADE).isoformat(timespec="seconds")


def now_dt() -> datetime:
    """Current Belgrade time as a datetime object (for calculations)."""
    return datetime.now(_BELGRADE)
