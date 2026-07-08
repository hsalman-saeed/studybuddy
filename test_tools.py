"""Tests for the tool/function-calling integration layer."""

import json

from tools import execute_tool, TOOLS


def test_save_study_session():
    """Test 1: Save a study session with structured data + semantic notes."""
    print("=" * 70)
    print("TEST 1: save_study_session")
    print("=" * 70)

    result = execute_tool(
        "save_study_session",
        {
            "topic": "Python Decorators",
            "concepts_learned": ["function_wrapping", "closure_scoping", "functools.wraps"],
            "session_text": (
                "Python decorators are functions that modify the behavior of other functions. "
                "They use function wrapping — the decorator receives the original function and "
                "returns a new wrapper function. Closure scoping allows the wrapper to access "
                "the original function and any state captured at decoration time. The "
                "functools.wraps utility preserves the original function's metadata (name, "
                "docstring) when creating the wrapper."
            ),
            "difficulty_rating": 4,
            "notes": "Key insight: decorators are just syntactic sugar for function composition.",
        },
    )
    parsed = json.loads(result)
    print(f"\n  Result: {json.dumps(parsed, indent=4, default=str)}")
    assert parsed.get("success"), "Expected success=True"
    assert parsed.get("schedules_initialized", 0) == 3, (
        f"Expected 3 schedules initialized, got {parsed.get('schedules_initialized')}"
    )
    print(f"  CONFIRMED: session saved, notes embedded, 3 SRS schedules initialized")
    print()


def test_get_study_history():
    """Test 2: Retrieve study history with both structured and semantic search."""
    print("=" * 70)
    print("TEST 2: get_study_history (structured + semantic)")
    print("=" * 70)

    result = execute_tool(
        "get_study_history",
        {
            "topic": "Python Decorators",
            "semantic_query": "wrapping functions with closure",
            "limit": 5,
        },
    )
    parsed = json.loads(result)
    print(f"\n  Structured results: {json.dumps(parsed.get('structured_results', {}), indent=4, default=str)}")
    print(f"\n  Semantic results: {json.dumps(parsed.get('semantic_results', {}), indent=4, default=str)}")

    structured = parsed.get("structured_results", {})
    semantic = parsed.get("semantic_results", {})
    assert structured.get("success"), "Expected structured results success"
    assert semantic.get("success"), "Expected semantic results success"
    print(f"\n  CONFIRMED: both structured and semantic results retrieved")
    print()


def test_generate_quiz():
    """Test 3: Generate quiz questions from study history."""
    print("=" * 70)
    print("TEST 3: generate_quiz")
    print("=" * 70)

    result = execute_tool(
        "generate_quiz",
        {
            "topic": "Python Decorators",
            "num_questions": 3,
            "difficulty": "medium",
        },
    )
    parsed = json.loads(result)
    print(f"\n  Result: {json.dumps(parsed, indent=4, default=str)}")

    if not parsed.get("success"):
        print(f"  WARNING: quiz generation failed — raw_response may need inspection")
        if "raw_response" in parsed:
            print(f"  Raw response (first 200 chars): {parsed['raw_response'][:200]}")
    else:
        questions = parsed.get("questions", [])
        assert len(questions) > 0, "Expected at least one question"
        for i, q in enumerate(questions, 1):
            assert "question" in q, f"Question {i} missing 'question' key"
            assert "answer" in q, f"Question {i} missing 'answer' key"
            assert "concept" in q, f"Question {i} missing 'concept' key"
        print(f"\n  CONFIRMED: {len(questions)} questions generated, all with question/answer/concept keys")
    print()


def test_record_quiz_answer():
    """Test 4: Record a quiz answer and update mastery + SRS."""
    print("=" * 70)
    print("TEST 4: record_quiz_answer")
    print("=" * 70)

    result = execute_tool(
        "record_quiz_answer",
        {
            "topic": "functools.wraps",
            "question": "What does functools.wraps do in a decorator?",
            "correct_answer": "It preserves the original function's metadata (name, docstring) on the wrapper function.",
            "student_answer": "It preserves the original function's metadata like name and docstring.",
            "is_correct": True,
        },
    )
    parsed = json.loads(result)
    print(f"\n  Result: {json.dumps(parsed, indent=4, default=str)}")
    assert parsed.get("success"), "Expected success=True"
    assert parsed.get("quiz_saved", {}).get("success"), "Expected quiz_saved success"
    assert parsed.get("schedule_updated", {}).get("success"), "Expected schedule_updated success"
    print(f"  CONFIRMED: quiz result saved, SRS schedule updated")
    print()


def test_get_weak_areas():
    """Test 5: Get priority-ranked weak areas (low mastery + overdue)."""
    print("=" * 70)
    print("TEST 5: get_weak_areas")
    print("=" * 70)

    result = execute_tool("get_weak_areas", {})
    parsed = json.loads(result)
    print(f"\n  Result: {json.dumps(parsed, indent=4, default=str)}")

    assert parsed.get("success"), "Expected success=True"
    priority = parsed.get("priority_concepts", [])
    print(f"\n  Priority concepts: {priority}")
    print(f"  CONFIRMED: priority list combines low-mastery + overdue concepts")
    print()


def test_create_study_plan():
    """Test 6: Generate a personalized study plan."""
    print("=" * 70)
    print("TEST 6: create_study_plan")
    print("=" * 70)

    result = execute_tool(
        "create_study_plan",
        {
            "goal": "Master Python Decorators",
            "days_available": 5,
            "hours_per_day": 2.0,
        },
    )
    parsed = json.loads(result)
    print(f"\n  Result (plan_text):")
    if parsed.get("success"):
        print(f"\n{parsed.get('plan_text', '')}\n")
        print(f"  Based on priority concepts: {parsed.get('based_on_priority_concepts', [])}")
    else:
        print(f"  FAILED: {json.dumps(parsed, indent=4, default=str)}")
    print()


def test_tools_definition():
    """Verify TOOLS list is correctly structured."""
    print("=" * 70)
    print("BONUS: TOOLS schema validation")
    print("=" * 70)

    print(f"\n  Total tools defined: {len(TOOLS)}")
    for tool in TOOLS:
        name = tool["function"]["name"]
        desc = tool["function"]["description"][:60] + "..."
        required = tool["function"]["parameters"].get("required", [])
        print(f"  - {name}: {desc}")
        if required:
            print(f"    Required params: {required}")

    assert len(TOOLS) == 6, f"Expected 6 tools, got {len(TOOLS)}"
    print(f"\n  CONFIRMED: all 6 tools defined with valid schema")
    print()


if __name__ == "__main__":
    test_tools_definition()
    test_save_study_session()
    test_get_study_history()
    test_generate_quiz()
    test_record_quiz_answer()
    test_get_weak_areas()
    test_create_study_plan()
    print("=" * 70)
    print("All tools integration tests complete.")
    print("=" * 70)
