"""Tests for the resilience/retry layer."""

import json

from resilience import classify_retryable_error, safe_generate, get_resilience_stats


def test_safe_generate_baseline():
    """Test 1: safe_generate() with a normal simple message — proves the happy path works."""
    print("=" * 60)
    print("TEST 1: safe_generate() — baseline happy path")
    print("=" * 60)

    result = safe_generate(
        messages=[{"role": "user", "content": "What is 2+2?"}],
        force_tier="simple",
    )
    print(f"\n  Result: {json.dumps(result, indent=2, default=str)}")
    assert "text" in result, "Missing 'text' key in result"
    assert result["text"], "'text' key is empty — expected actual content"
    assert result.get("success"), "Expected success=True"
    print(f"  CONFIRMED: 'text' key present with real content")
    print()


def test_classify_retryable_error():
    """Test 2: classify_retryable_error() with various fake exceptions."""
    print("=" * 60)
    print("TEST 2: classify_retryable_error()")
    print("=" * 60)

    test_cases = [
        (TimeoutError("Connection timed out after 30s"), True, "TimeoutError"),
        (Exception("Rate limit exceeded — please retry"), True, "Rate limit"),
        (Exception("Connection refused by server"), True, "Connection refused"),
        (Exception("502 Bad Gateway"), True, "502 server error"),
        (Exception("Invalid API key provided"), False, "Invalid API key"),
        (Exception("401 Unauthorized — authentication failed"), False, "401 auth"),
        (Exception("400 Bad Request — malformed input"), False, "400 bad request"),
        (Exception("Content policy violation"), False, "Content policy"),
    ]

    for exc, expected, label in test_cases:
        result = classify_retryable_error(exc)
        status = "PASS" if result == expected else "FAIL"
        print(f"  [{status}] {label}: {result} (expected {expected})")

    print()


def test_resilience_stats():
    """Test 3: get_resilience_stats() after previous calls."""
    print("=" * 60)
    print("TEST 3: get_resilience_stats()")
    print("=" * 60)

    stats = get_resilience_stats()
    print(f"\n  Stats: {json.dumps(stats, indent=2)}")
    print(f"  Total calls: {stats['total_calls']}")
    print(f"  Retries triggered: {stats['total_retries_triggered']}")
    print(f"  Non-retryable failures: {stats['total_non_retryable_failures']}")
    print(f"  Complete failures: {stats['total_complete_failures']}")
    print()


if __name__ == "__main__":
    test_safe_generate_baseline()
    test_classify_retryable_error()
    test_resilience_stats()
    print("All resilience tests complete.")
