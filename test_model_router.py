"""Tests for the model-routing layer."""

import json

from model_router import classify_complexity, generate, get_routing_stats


def test_classify_complexity():
    """Test 1: Classifier with obviously simple and obviously complex messages."""
    print("=" * 60)
    print("TEST 1: classify_complexity()")
    print("=" * 60)

    simple_msg = "Hi, how are you?"
    simple_result = classify_complexity(simple_msg)
    print(f"\n  Simple message: \"{simple_msg}\"")
    print(f"  Result: {json.dumps(simple_result, indent=4)}")

    complex_msg = (
        "Analyze my last 5 study sessions and create a personalized 7-day review plan "
        "prioritizing my weakest concepts"
    )
    complex_result = classify_complexity(complex_msg)
    print(f"\n  Complex message: \"{complex_msg}\"")
    print(f"  Result: {json.dumps(complex_result, indent=4)}")

    print()


def test_generate_simple():
    """Test 2: generate() with a simple message — should use DEFAULT_MODEL."""
    print("=" * 60)
    print("TEST 2: generate() — simple message")
    print("=" * 60)

    result = generate(
        messages=[{"role": "user", "content": "What is the capital of France?"}],
        force_tier="simple",
    )
    print(f"\n  Result: {json.dumps(result, indent=2, default=str)}")
    assert result.get("model_used") == "qwen3.7-plus", (
        f"Expected qwen3.7-plus, got {result.get('model_used')}"
    )
    print(f"  CONFIRMED: model_used is qwen3.7-plus")
    print()


def test_generate_complex():
    """Test 3: generate() with a complex message — should use COMPLEX_MODEL."""
    print("=" * 60)
    print("TEST 3: generate() — complex message")
    print("=" * 60)

    result = generate(
        messages=[
            {
                "role": "user",
                "content": "Analyze my study patterns and create a review plan",
            }
        ],
        force_tier="complex",
    )
    print(f"\n  Result: {json.dumps(result, indent=2, default=str)}")
    assert result.get("model_used") == "qwen3.7-max", (
        f"Expected qwen3.7-max, got {result.get('model_used')}"
    )
    print(f"  CONFIRMED: model_used is qwen3.7-max")
    print()


def test_routing_stats():
    """Test 4: get_routing_stats() after previous calls."""
    print("=" * 60)
    print("TEST 4: get_routing_stats()")
    print("=" * 60)

    stats = get_routing_stats()
    print(f"\n  Stats: {json.dumps(stats, indent=2)}")
    print(f"  Total calls: {stats['total_calls']}")
    print(f"  Simple tier: {stats['simple_tier_count']}")
    print(f"  Complex tier: {stats['complex_tier_count']}")
    print(f"  Fallback used: {stats['fallback_used_count']}")
    print(f"  Per-model usage: {stats['per_model_usage']}")
    print()


if __name__ == "__main__":
    test_classify_complexity()
    test_generate_simple()
    test_generate_complex()
    test_routing_stats()
    print("All model router tests complete.")
