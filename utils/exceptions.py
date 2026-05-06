# utils/exceptions.py

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
    """Failed to parse valid configuration JSON files."""
    pass

class EmptyResponse(VibeGuardError):
    """Model returned an empty response."""
    pass

class FileSystemError(VibeGuardError):
    """Failed to write or read from disk."""
    pass

class EventError(VibeGuardError):
    """Unexpected event occured."""
    pass

class MissingFeatureId(VibeGuardError):
    """Feature ID does not exist in map."""
    pass
