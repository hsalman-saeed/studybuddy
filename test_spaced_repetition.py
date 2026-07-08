"""Tests for the spaced-repetition scheduling engine (SM-2 algorithm)."""

import json
from datetime import date, timedelta

from memory_sqlite import MemoryManager
from spaced_repetition import calculate_sm2, SpacedRepetitionEngine


def test_calculate_sm2_sequence():
    """Test 1: Pure SM-2 calculation with a sequence of quality scores."""
    print("=" * 60)
    print("TEST 1: calculate_sm2() pure function — interval progression")
    print("=" * 60)

    quality_sequence = [4, 5, 5, 2, 4]
    ease_factor = 2.5
    interval_days = 1
    review_count = 0

    for i, quality in enumerate(quality_sequence, 1):
        result = calculate_sm2(quality, ease_factor, interval_days, review_count)
        print(
            f"  Step {i}: quality={quality}  |  "
            f"ease_factor: {ease_factor} → {result['ease_factor']}  |  "
            f"interval: {interval_days} → {result['interval_days']}  |  "
            f"review_count: {review_count} → {result['review_count']}"
        )
        ease_factor = result["ease_factor"]
        interval_days = result["interval_days"]
        review_count = result["review_count"]

    print()


def test_process_review_workflow():
    """Tests 2-5: Full engine workflow with real DB persistence."""
    print("=" * 60)
    print("TEST 2-5: SpacedRepetitionEngine — full DB workflow")
    print("=" * 60)

    engine = SpacedRepetitionEngine()
    memory = MemoryManager()
    concept = "test_concept"

    # Test 2: Save a study session to create the concept
    print("\n--- Test 2: Save study session ---")
    save_result = memory.save_study_session(
        topic="Test Topic",
        concepts_learned=[concept],
        difficulty_rating=3,
        notes="Test concept for spaced repetition",
    )
    print(f"  save_study_session: {json.dumps(save_result, indent=2)}")

    # Test 3: Initialize new concept schedule
    print("\n--- Test 3: Initialize new concept schedule ---")
    init_result = engine.initialize_new_concept_schedule(concept)
    print(f"  initialize_new_concept_schedule: {json.dumps(init_result, indent=2)}")

    # Verify the concept was initialized
    concept_data = memory.get_concept(concept)
    expected_next_review = (date.today() + timedelta(days=1)).isoformat()
    print(f"  next_review_date set to: {concept_data.get('next_review_date')} (expected: {expected_next_review})")
    print(f"  interval_days: {concept_data.get('interval_days')} (expected: 1)")

    # Test 4: Process three correct reviews — intervals should grow (1 → 6 → larger)
    print("\n--- Test 4: Three correct reviews — interval growth ---")
    for i in range(1, 4):
        result = engine.process_review(concept, is_correct=True)
        print(f"  Review {i}: {json.dumps(result, indent=2)}")

    # Test 5: Process one incorrect review — interval should reset to 1
    print("\n--- Test 5: Incorrect review — interval reset ---")
    result = engine.process_review(concept, is_correct=False)
    print(f"  Incorrect review: {json.dumps(result, indent=2)}")

    # Final state check
    final_concept = memory.get_concept(concept)
    print(f"\n  Final concept state:")
    print(f"    interval_days: {final_concept['interval_days']} (expected: 1 after reset)")
    print(f"    review_count: {final_concept['review_count']} (expected: 0 after reset)")
    print(f"    ease_factor: {final_concept['ease_factor']} (reduced due to incorrect answer)")

    print()


if __name__ == "__main__":
    test_calculate_sm2_sequence()
    test_process_review_workflow()
    print("All spaced repetition tests complete.")
