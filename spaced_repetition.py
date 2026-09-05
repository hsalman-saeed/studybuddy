"""Spaced-repetition scheduling engine based on the SM-2 algorithm (Ebbinghaus forgetting curve).

This models the Ebbinghaus forgetting curve by increasing review spacing exponentially for
well-remembered concepts and resetting spacing to daily for forgotten ones — this is why the
system is called a spaced-repetition memory engine, not just a chatbot with a database.
"""

from datetime import date, timedelta

from memory_sqlite import DEFAULT_STUDENT_ID, MemoryManager


def calculate_sm2(quality: int, ease_factor: float, interval_days: int, review_count: int) -> dict:
    """Pure-function SM-2 calculation — no database or class dependency.

    quality: 0-5 (0=total blackout, 5=perfect recall)
    ease_factor: current ease factor (minimum 1.3)
    interval_days: current interval in days
    review_count: number of successful reviews so far

    Returns dict with new_ease, new_interval, new_review_count.
    """
    # 1. Update ease_factor
    new_ease = ease_factor + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
    new_ease = max(new_ease, 1.3)  # never let ease drop below 1.3

    # 2. Determine new interval and review_count
    if quality < 3:
        # Poor recall — treat as "forgotten"
        new_review_count = 0
        new_interval = 1
    else:
        # Good recall — treat as "remembered"
        new_review_count = review_count + 1
        if new_review_count == 1:
            new_interval = 1
        elif new_review_count == 2:
            new_interval = 6
        else:
            new_interval = round(interval_days * new_ease)

    return {
        "ease_factor": round(new_ease, 4),
        "interval_days": new_interval,
        "review_count": new_review_count,
    }


class SpacedRepetitionEngine:
    """Ebbinghaus-forgetting-curve-based scheduler using the SM-2 algorithm."""

    def __init__(self):
        self.memory = MemoryManager()

    def process_review(self, concept_name: str, is_correct: bool, quality: int = None, student_id: str = DEFAULT_STUDENT_ID) -> dict:
        """Process a review event for a scoped concept, updating its spaced-repetition schedule.

        If quality is None, derive it: quality = 4 if is_correct else 1.
        """
        try:
            if quality is None:
                quality = 4 if is_correct else 1

            concept = self.memory.get_concept(concept_name, student_id=student_id)
            if "error" in concept:
                return {"success": False, "error": "concept not found — must be studied via save_study_session first"}

            old_interval = concept["interval_days"]
            old_ease = concept["ease_factor"]
            old_review_count = concept["review_count"]

            sm2_result = calculate_sm2(
                quality=quality,
                ease_factor=old_ease,
                interval_days=old_interval,
                review_count=old_review_count,
            )

            new_interval = sm2_result["interval_days"]
            new_ease = sm2_result["ease_factor"]
            new_review_count = sm2_result["review_count"]

            next_review_date = (date.today() + timedelta(days=new_interval)).isoformat()

            update_result = self.memory.update_review_schedule(
                concept_name=concept_name,
                ease_factor=new_ease,
                interval_days=new_interval,
                next_review_date=next_review_date,
                review_count=new_review_count,
                student_id=student_id,
            )

            if not update_result.get("success"):
                return update_result

            return {
                "success": True,
                "concept": concept_name,
                "previous_interval": old_interval,
                "new_interval": new_interval,
                "next_review_date": next_review_date,
                "ease_factor": new_ease,
                "review_count": new_review_count,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_due_concepts(self, student_id: str = DEFAULT_STUDENT_ID) -> dict:
        """Return scoped concepts whose next_review_date is today or earlier."""
        return self.memory.get_concepts_due_for_review(student_id=student_id)

    def initialize_new_concept_schedule(self, concept_name: str, student_id: str = DEFAULT_STUDENT_ID) -> dict:
        """Initialize the review schedule for a scoped concept that hasn't been reviewed yet.

        Sets next_review_date to tomorrow, interval_days stays 1.
        """
        concept = self.memory.get_concept(concept_name, student_id=student_id)
        if "error" in concept:
            return {"success": False, "error": "concept not found"}

        tomorrow = (date.today() + timedelta(days=1)).isoformat()

        return self.memory.update_review_schedule(
            concept_name=concept_name,
            ease_factor=2.5,
            interval_days=1,
            next_review_date=tomorrow,
            review_count=0,
            student_id=student_id,
        )
