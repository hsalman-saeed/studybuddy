"""Compare stateless Qwen answers against StudyBuddy's memory-aware pipeline.

The evaluation focuses on the hackathon criterion that StudyBuddy should build a
student's skill and retention by responding to the student's actual mastery state,
not treating all studied material as equally known.

Run:
    python eval_skill_building.py

Outputs:
    - Console summary table
    - eval_results.json with raw prompts, responses, and scores
"""

import json
import re
from datetime import datetime

from memory_sqlite import MemoryManager
from resilience import safe_generate

EVAL_STUDENT_ID = f"eval_skill_building_student_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

SCENARIOS = [
    {
        "id": "s01",
        "question": "What should I review before my Python quiz tomorrow?",
        "topic": "Python Functions",
        "weak_concept": "scope",
        "strong_concept": "function parameters",
        "expected_terms": ["scope", "mastery", "review"],
    },
    {
        "id": "s02",
        "question": "Can you choose one algebra concept for me to retry?",
        "topic": "Algebra Linear Equations",
        "weak_concept": "checking solutions",
        "strong_concept": "inverse operations",
        "expected_terms": ["checking solutions", "retry", "mastery"],
    },
    {
        "id": "s03",
        "question": "I have 20 minutes. What biology practice should I do?",
        "topic": "Biology Cell Structure",
        "weak_concept": "mitochondria",
        "strong_concept": "nucleus",
        "expected_terms": ["mitochondria", "practice", "mastery"],
    },
    {
        "id": "s04",
        "question": "Which calculus topic is most urgent for me?",
        "topic": "Calculus Derivatives",
        "weak_concept": "chain rule",
        "strong_concept": "power rule",
        "expected_terms": ["chain rule", "urgent", "review"],
    },
    {
        "id": "s05",
        "question": "Make my next chemistry question target my weakest area.",
        "topic": "Chemistry Bonding",
        "weak_concept": "polar covalent bonds",
        "strong_concept": "ionic bonds",
        "expected_terms": ["polar covalent", "weak", "question"],
    },
    {
        "id": "s06",
        "question": "What Spanish grammar should I retry today?",
        "topic": "Spanish Grammar",
        "weak_concept": "preterite tense",
        "strong_concept": "present tense",
        "expected_terms": ["preterite", "retry", "today"],
    },
    {
        "id": "s07",
        "question": "Which statistics concept needs feedback-driven practice?",
        "topic": "Statistics Basics",
        "weak_concept": "standard deviation",
        "strong_concept": "mean",
        "expected_terms": ["standard deviation", "feedback", "practice"],
    },
    {
        "id": "s08",
        "question": "I want a quick review plan for computer networks.",
        "topic": "Computer Networks",
        "weak_concept": "TCP handshake",
        "strong_concept": "IP address",
        "expected_terms": ["TCP handshake", "review", "practice"],
    },
    {
        "id": "s09",
        "question": "What should I not waste time on because I already know it?",
        "topic": "World History",
        "weak_concept": "Treaty of Versailles",
        "strong_concept": "Industrial Revolution",
        "expected_terms": ["Industrial Revolution", "already", "master"],
    },
    {
        "id": "s10",
        "question": "Pick my next physics retry target.",
        "topic": "Physics Motion",
        "weak_concept": "acceleration graphs",
        "strong_concept": "velocity definition",
        "expected_terms": ["acceleration graphs", "retry", "target"],
    },
    {
        "id": "s11",
        "question": "How should I practice essay writing based on my past mistakes?",
        "topic": "Essay Writing",
        "weak_concept": "thesis specificity",
        "strong_concept": "paragraph transitions",
        "expected_terms": ["thesis specificity", "mistakes", "practice"],
    },
    {
        "id": "s12",
        "question": "Which data structures topic should come first in my study block?",
        "topic": "Data Structures",
        "weak_concept": "hash collisions",
        "strong_concept": "arrays",
        "expected_terms": ["hash collisions", "first", "study"],
    },
    {
        "id": "s13",
        "question": "What economics concept is due for review?",
        "topic": "Microeconomics",
        "weak_concept": "elasticity",
        "strong_concept": "supply curve",
        "expected_terms": ["elasticity", "due", "review"],
    },
    {
        "id": "s14",
        "question": "Give me a targeted retry suggestion for SQL.",
        "topic": "SQL Joins",
        "weak_concept": "left join null handling",
        "strong_concept": "inner joins",
        "expected_terms": ["left join", "retry", "null"],
    },
    {
        "id": "s15",
        "question": "What should my next flashcard be about?",
        "topic": "Anatomy",
        "weak_concept": "neuron synapse",
        "strong_concept": "bone names",
        "expected_terms": ["neuron synapse", "flashcard", "mastery"],
    },
]


def seed_scenario(memory, scenario):
    """Create scoped memory rows with one high-mastery and one low-mastery concept."""
    memory.save_study_session(
        scenario["topic"],
        [scenario["weak_concept"], scenario["strong_concept"]],
        difficulty_rating=3,
        notes=f"Studied {scenario['weak_concept']} and {scenario['strong_concept']}.",
        student_id=EVAL_STUDENT_ID,
    )

    for _ in range(7):
        memory.save_quiz_result(
            scenario["strong_concept"],
            "Prior mastery check",
            "correct",
            "correct",
            True,
            student_id=EVAL_STUDENT_ID,
        )
    for _ in range(3):
        memory.save_quiz_result(
            scenario["weak_concept"],
            "Prior mastery check",
            "correct",
            "missed",
            False,
            student_id=EVAL_STUDENT_ID,
        )


def build_pipeline_context(memory, scenario):
    """Read StudyBuddy memory for the exact state the response should use."""
    weak = memory.get_concept(scenario["weak_concept"], student_id=EVAL_STUDENT_ID)
    strong = memory.get_concept(scenario["strong_concept"], student_id=EVAL_STUDENT_ID)
    weak_areas = memory.get_weak_areas(limit=5, student_id=EVAL_STUDENT_ID)
    return {
        "weak_concept_state": weak,
        "strong_concept_state": strong,
        "priority_concepts": [item["concept_name"] for item in weak_areas.get("weak_areas", [])],
    }


def call_qwen(messages):
    """Call Qwen through the existing resilience layer."""
    result = safe_generate(messages=messages, force_tier="default")
    if result.get("success"):
        return result.get("text", "")
    return f"ERROR: {result.get('error', result)}"


def _number_words(number: int) -> list[str]:
    """Return simple English variants for small integer evidence matching."""
    words = {
        0: "zero",
        1: "one",
        2: "two",
        3: "three",
        4: "four",
        5: "five",
        6: "six",
        7: "seven",
        8: "eight",
        9: "nine",
        10: "ten",
    }
    return [str(number), words.get(number, str(number))]


def _contains_phrase(response: str, phrase: str) -> bool:
    """Case-insensitive phrase match with whitespace normalized."""
    normalized_response = re.sub(r"\s+", " ", response.lower())
    normalized_phrase = re.sub(r"\s+", " ", phrase.lower()).strip()
    return normalized_phrase in normalized_response


def _tokens(text: str) -> list[str]:
    """Return lowercase word/number tokens for proximity scoring."""
    return re.findall(r"\b[\w']+\b", text.lower())


def _number_token_set(number: int) -> set[str]:
    """Return accepted numeric tokens for one stored evidence number."""
    return set(_number_words(int(number)))


def _concept_spans(response_tokens: list[str], concept: str) -> list[tuple[int, int]]:
    """Return token spans where the target concept appears."""
    concept_tokens = _tokens(concept)
    if not concept_tokens:
        return []

    spans = []
    width = len(concept_tokens)
    for index in range(0, len(response_tokens) - width + 1):
        if response_tokens[index:index + width] == concept_tokens:
            spans.append((index, index + width - 1))
    return spans


def _specific_number_near_concept(response: str, concept: str, number: int, window_words: int = 12) -> bool:
    """Require the target concept and exact stored number to appear close together.

    This accepts natural wording such as "mastery level of 0 for mitochondria"
    while still rejecting vague claims that omit the actual stored number.
    """
    response_tokens = _tokens(response)
    spans = _concept_spans(response_tokens, concept)
    number_tokens = _number_token_set(number)
    number_positions = [index for index, token in enumerate(response_tokens) if token in number_tokens]

    for start, end in spans:
        for number_index in number_positions:
            if start - window_words <= number_index <= end + window_words:
                return True

    sentences = re.split(r"(?<=[.!?])\s+", response)
    for sentence in sentences:
        sentence_tokens = _tokens(sentence)
        if _contains_phrase(sentence, concept) and any(token in number_tokens for token in sentence_tokens):
            return True

    return False


def _evidence_hits_for(response: str, concept: str, concept_state: dict, target_kind: str) -> list[str]:
    """Find concrete stored mastery/performance numbers near the target concept."""
    evidence_hits = []
    mastery = concept_state.get("mastery_level")
    correct = concept_state.get("times_correct")
    wrong = concept_state.get("times_wrong")

    if mastery is not None and _specific_number_near_concept(response, concept, int(mastery)):
        evidence_hits.append(f"mastery_level={int(mastery)} near {concept}")

    if target_kind == "strong":
        if correct is not None and _specific_number_near_concept(response, concept, int(correct)):
            evidence_hits.append(f"times_correct={int(correct)} near {concept}")
    else:
        if wrong is not None and _specific_number_near_concept(response, concept, int(wrong)):
            evidence_hits.append(f"times_wrong={int(wrong)} near {concept}")

    return evidence_hits


def _required_evidence_examples(concept_state: dict, target_kind: str) -> list[str]:
    """Describe the exact stored numbers that can satisfy strict scoring."""
    examples = []
    mastery = concept_state.get("mastery_level")
    correct = concept_state.get("times_correct")
    wrong = concept_state.get("times_wrong")

    if mastery is not None:
        examples.append(f"target concept near mastery number {int(mastery)}")
    if target_kind == "strong" and correct is not None:
        examples.append(f"target concept near correct-count number {int(correct)}")
    if target_kind == "weak" and wrong is not None:
        examples.append(f"target concept near wrong-count number {int(wrong)}")

    return examples


def score_response(response, scenario, memory_context):
    """Strictly score whether the response uses memory-dependent evidence.

    A pass requires both:
    1. The correct scenario-specific target concept.
    2. The exact stored mastery or past-performance number near that concept.

    Generic study advice, broad educational language, or naming a plausible topic
    without a nearby stored number does not pass.
    """
    target_kind = "strong" if scenario["id"] == "s09" else "weak"
    target_concept = scenario[f"{target_kind}_concept"]
    concept_state = memory_context[f"{target_kind}_concept_state"]

    concept_hit = _contains_phrase(response, target_concept)
    evidence_hits = _evidence_hits_for(response, target_concept, concept_state, target_kind)
    passed = concept_hit and bool(evidence_hits)

    return {
        "passed": passed,
        "target_kind": target_kind,
        "target_concept": target_concept,
        "concept_hit": concept_hit,
        "evidence_hits": evidence_hits,
        "required_evidence_examples": _required_evidence_examples(concept_state, target_kind),
        "score": "1/1" if passed else "0/1",
    }


def run_scenario(memory, scenario):
    seed_scenario(memory, scenario)
    context = build_pipeline_context(memory, scenario)

    stateless_messages = [
        {
            "role": "system",
            "content": "You are a helpful study coach. You do not have access to the student's stored mastery data.",
        },
        {"role": "user", "content": scenario["question"]},
    ]
    pipeline_messages = [
        {
            "role": "system",
            "content": (
                "You are StudyBuddy. Use the provided memory state to recommend practice that reflects "
                "the student's actual mastery. Prefer low-mastery or due concepts over mastered ones."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Student question: {scenario['question']}\n\n"
                f"StudyBuddy memory state:\n{json.dumps(context, indent=2)}\n\n"
                "Respond in 3-5 sentences using the Prompt -> Practice -> Feedback -> Retry loop."
            ),
        },
    ]

    stateless_response = call_qwen(stateless_messages)
    pipeline_response = call_qwen(pipeline_messages)

    return {
        "scenario_id": scenario["id"],
        "question": scenario["question"],
        "expected_terms": scenario["expected_terms"],
        "memory_context": context,
        "stateless_response": stateless_response,
        "studybuddy_response": pipeline_response,
        "stateless_score": score_response(stateless_response, scenario, context),
        "studybuddy_score": score_response(pipeline_response, scenario, context),
    }


def print_summary(results):
    """Print a compact console table."""
    print("\nSkill-building evaluation summary")
    print("=" * 72)
    print(f"{'ID':<5} {'Expected target':<30} {'Stateless':<12} {'StudyBuddy':<12}")
    print("-" * 72)
    for result in results:
        expected = result["studybuddy_score"]["target_concept"]
        stateless = "PASS" if result["stateless_score"]["passed"] else "MISS"
        studybuddy = "PASS" if result["studybuddy_score"]["passed"] else "MISS"
        print(f"{result['scenario_id']:<5} {expected:<30} {stateless:<12} {studybuddy:<12}")
    print("-" * 72)
    stateless_passes = sum(1 for r in results if r["stateless_score"]["passed"])
    studybuddy_passes = sum(1 for r in results if r["studybuddy_score"]["passed"])
    print(f"Stateless passes: {stateless_passes}/{len(results)}")
    print(f"StudyBuddy passes: {studybuddy_passes}/{len(results)}")


def main():
    memory = MemoryManager()
    results = [run_scenario(memory, scenario) for scenario in SCENARIOS]
    output = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "student_id": EVAL_STUDENT_ID,
        "scenario_count": len(results),
        "results": results,
    }
    with open("eval_results.json", "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print_summary(results)
    print("\nRaw results saved to eval_results.json")


if __name__ == "__main__":
    main()
