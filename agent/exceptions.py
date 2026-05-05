# agent/exceptions.py

class VibeGuardError(Exception):
    """Base exception for all VibeGuard errors."""
    pass

class RateLimitReached(VibeGuardError):
    """API rate limit hit after all retries."""
    pass

class ModelTimeout(VibeGuardError):
    """Model took too long to respond."""
    pass

class ParsingFailed(VibeGuardError):
    """Failed to parse valid vision doc JSON."""
    pass

class EmptyResponse(VibeGuardError):
    """Model returned an empty response."""
    pass