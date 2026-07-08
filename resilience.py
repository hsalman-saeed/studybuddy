"""Resilience and retry layer that handles transient failures and backoff strategies."""

import time

from model_router import generate

# ── Module-level counters ───────────────────────────────────────────────

_stats = {
    "total_calls": 0,
    "total_retries_triggered": 0,
    "total_non_retryable_failures": 0,
    "total_complete_failures": 0,
}


# ── Error classification ────────────────────────────────────────────────

def classify_retryable_error(exception: Exception) -> bool:
    """Decide if an exception is worth retrying (transient) or not (permanent)."""
    msg = str(exception).lower()
    exc_type = type(exception).__name__.lower()

    # Non-retryable: authentication errors
    auth_signals = [
        "invalid api key", "invalid_api_key", "invalidapikey",
        "401", "unauthorized", "authentication",
        "permission_denied", "permission denied",
        "access denied", "forbidden",
    ]
    for signal in auth_signals:
        if signal in msg:
            return False

    # Non-retryable: invalid request (malformed input won't fix itself)
    invalid_request_signals = [
        "invalid request", "invalid_request", "bad request",
        "400", "malformed",
    ]
    for signal in invalid_request_signals:
        if signal in msg:
            return False

    # Non-retryable: content policy violations
    policy_signals = [
        "content_policy", "content policy", "policy_violation",
        "blocked", "unsafe", "flagged",
    ]
    for signal in policy_signals:
        if signal in msg:
            return False

    # Retryable: rate limits
    rate_limit_signals = [
        "rate limit", "rate_limit", "ratelimit",
        "too many requests", "429", "throttl",
    ]
    for signal in rate_limit_signals:
        if signal in msg:
            return True

    # Retryable: timeouts
    timeout_signals = [
        "timeout", "timed out", "connecttimeout",
        "readtimeout", "deadline", "504",
    ]
    for signal in timeout_signals:
        if signal in msg:
            return True

    # Retryable: connection errors
    connection_signals = [
        "connection", "connect", "network",
        "unreachable", "refused", "reset",
        "ssl", "certificate",
    ]
    for signal in connection_signals:
        if signal in msg:
            return True

    # Retryable: 5xx server errors
    server_error_signals = [
        "500", "502", "503", "internal server error",
        "bad gateway", "service unavailable", "server error",
    ]
    for signal in server_error_signals:
        if signal in msg:
            return True

    # Retryable: transient/temporary errors
    transient_signals = [
        "transient", "temporary", "try again", "retry",
        "overload", "busy",
    ]
    for signal in transient_signals:
        if signal in msg:
            return True

    # Also check exception type names for common retryable types
    retryable_types = ["timeout", "connection", "ssl", "network"]
    for t in retryable_types:
        if t in exc_type:
            return True

    # Default: treat unknown errors as non-retryable to avoid wasting time
    return False


# ── Retry-wrapped generation ────────────────────────────────────────────

def resilient_generate(messages: list, force_tier: str = None, max_attempts: int = 3) -> dict:
    """Wrap model_router.generate() with exponential-backoff retry logic."""
    _stats["total_calls"] += 1

    attempt = 1
    last_error = None

    while attempt <= max_attempts:
        try:
            result = generate(messages=messages, force_tier=force_tier)

            # Treat a clean failure dict the same as an exception for retry
            if not result.get("success"):
                error_msg = result.get("error", "unknown error")
                # Check if the underlying error is retryable
                fake_exc = Exception(error_msg)
                if not classify_retryable_error(fake_exc):
                    _stats["total_non_retryable_failures"] += 1
                    result["retryable"] = False
                    result["attempts_made"] = attempt
                    return result

                # Retryable failure — continue retrying
                if attempt < max_attempts:
                    wait = 2 ** attempt  # 2s, 4s, ...
                    print(f"[Resilience] Attempt {attempt} failed ({error_msg}), retrying in {wait}s...")
                    _stats["total_retries_triggered"] += 1
                    time.sleep(wait)
                    attempt += 1
                    continue
                else:
                    _stats["total_complete_failures"] += 1
                    return {
                        "success": False,
                        "error": "all retry attempts exhausted",
                        "attempts_made": max_attempts,
                    }

            # Success
            result["attempts_made"] = attempt
            return result

        except Exception as e:
            last_error = e
            if not classify_retryable_error(e):
                _stats["total_non_retryable_failures"] += 1
                return {
                    "success": False,
                    "error": str(e),
                    "attempts_made": attempt,
                    "retryable": False,
                }

            # Retryable exception
            if attempt < max_attempts:
                wait = 2 ** attempt  # 2s, 4s, ...
                print(f"[Resilience] Attempt {attempt} failed ({e}), retrying in {wait}s...")
                _stats["total_retries_triggered"] += 1
                time.sleep(wait)
                attempt += 1
            else:
                _stats["total_complete_failures"] += 1
                return {
                    "success": False,
                    "error": f"all retry attempts exhausted: {e}",
                    "attempts_made": max_attempts,
                }

    # Should not reach here, but just in case
    _stats["total_complete_failures"] += 1
    return {
        "success": False,
        "error": f"all retry attempts exhausted: {last_error}",
        "attempts_made": max_attempts,
    }


# ── Safe wrapper (bulletproof — never raises) ───────────────────────────

def safe_generate(messages: list, force_tier: str = None) -> dict:
    """The function all other files should call. Never raises, always returns a dict with 'text' key."""
    try:
        result = resilient_generate(messages=messages, force_tier=force_tier)
        # Guarantee 'text' key exists
        if "text" not in result:
            if result.get("success"):
                result["text"] = ""
            else:
                result["text"] = "I'm having trouble connecting right now — please try again in a moment."
        return result
    except Exception as e:
        # Bulletproof outer catch — should never happen, but just in case
        return {
            "success": False,
            "error": str(e),
            "text": "I'm having trouble connecting right now — please try again in a moment.",
            "attempts_made": 1,
        }


# ── Stats ───────────────────────────────────────────────────────────────

def get_resilience_stats() -> dict:
    """Return current resilience counters."""
    return dict(_stats)
