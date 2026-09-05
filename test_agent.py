"""Tests for the conversational agent orchestration layer."""

import json
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from agent import StudyBuddyAgent


def run_conversation_test():
    """Run a full multi-turn conversation through the agent."""

    # Step 0: Create agent
    print("=" * 70)
    print("STEP 0: Creating StudyBuddyAgent")
    print("=" * 70)
    agent = StudyBuddyAgent()
    print()

    # Step 1: Describe a study session (should trigger save_study_session)
    print("=" * 70)
    print("STEP 1: Student describes studying Python generators")
    print("=" * 70)
    response = agent.chat(
        "Hi! I just spent an hour learning about Python generators. "
        "I learned about yield, generator expressions, and lazy evaluation."
    )
    print(f"\n  Agent response:\n  {response}\n")
    print("  [Check console above for '[Agent] Calling tool: save_study_session']")
    print()

    # Step 2: Ask for a quiz (should trigger generate_quiz)
    print("=" * 70)
    print("STEP 2: Student asks for a quiz on generators")
    print("=" * 70)
    response = agent.chat("Can you quiz me on generators?")
    print(f"\n  Agent response:\n  {response}\n")
    print("  [Check console above for '[Agent] Calling tool: generate_quiz']")
    print()

    # Step 3: Answer the first quiz question
    print("=" * 70)
    print("STEP 3: Student answers the first quiz question")
    print("=" * 70)

    # The quiz question was about generators — provide a knowledgeable answer
    # that demonstrates understanding (the agent should judge this as correct).
    # We don't try to extract a "correct answer" from the quiz response since
    # the agent intentionally doesn't reveal answers during a quiz.
    student_answer = (
        "When a generator function hits yield, it pauses execution and saves "
        "its entire state — all local variables and the instruction pointer. "
        "The next time you call next() on it, it resumes right where it left off."
    )

    print(f"  Formulated student answer: \"{student_answer}\"")
    response = agent.chat(student_answer)
    print(f"\n  Agent response:\n  {response}\n")
    print("  [Check console above for '[Agent] Calling tool: record_quiz_answer']")
    print()

    # Step 4: Ask what to focus on next (should trigger get_weak_areas)
    print("=" * 70)
    print("STEP 4: Student asks what to focus on next")
    print("=" * 70)
    response = agent.chat("What should I focus on studying next?")
    print(f"\n  Agent response:\n  {response}\n")
    print("  [Check console above for '[Agent] Calling tool: get_weak_areas']")
    print()

    # Step 5: Session summary
    print("=" * 70)
    print("STEP 5: Session summary")
    print("=" * 70)
    summary = agent.get_session_summary()
    print(f"\n  Session summary: {json.dumps(summary, indent=4, default=str)}")
    print()

    print("=" * 70)
    print("Agent conversation test complete.")
    print("=" * 70)


if __name__ == "__main__":
    run_conversation_test()
