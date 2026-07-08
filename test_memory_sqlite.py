"""Standalone smoke test for MemoryManager — saves fake data and prints stats."""

import os
import sys

# Use a throwaway DB so we don't pollute the real one
os.environ["DB_PATH"] = "test_memory.db"

from memory_sqlite import MemoryManager

mm = MemoryManager()

# 1. Save a fake study session
print("\n--- save_study_session ---")
result = mm.save_study_session(
    topic="Python Basics",
    concepts_learned=["variables", "loops", "functions"],
    difficulty_rating=3,
    notes="First session",
)
print(result)

# 2. Save a second session to build up data
result = mm.save_study_session(
    topic="Python Basics",
    concepts_learned=["variables", "classes"],
    difficulty_rating=4,
    notes="Follow-up",
)
print(result)

# 3. Save quiz results (one correct, one wrong)
print("\n--- save_quiz_result ---")
r1 = mm.save_quiz_result(
    topic="variables",
    question="What is a variable?",
    correct_answer="A named storage location",
    student_answer="A named storage location",
    is_correct=True,
)
print("quiz (correct):", r1)

r2 = mm.save_quiz_result(
    topic="loops",
    question="What does a for loop do?",
    correct_answer="Iterates over a sequence",
    student_answer="It loops forever",
    is_correct=False,
)
print("quiz (wrong):", r2)

# 4. Print overall stats
print("\n--- get_overall_stats ---")
print(mm.get_overall_stats())

# 5. Print weak areas
print("\n--- get_weak_areas ---")
print(mm.get_weak_areas())

# 6. Verify review list is empty (spaced_repetition hasn't run yet)
print("\n--- get_concepts_due_for_review ---")
print(mm.get_concepts_due_for_review())

# Cleanup
os.remove("test_memory.db")
print("\nTest DB cleaned up.")
