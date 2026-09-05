"""Tool and function-calling layer that exposes callable actions to the agent."""

import json
from uuid import uuid4

from memory_sqlite import DEFAULT_STUDENT_ID, MemoryManager
from memory_vector import VectorMemoryManager
from spaced_repetition import SpacedRepetitionEngine
from resilience import safe_generate

# ── Module-level instances ──────────────────────────────────────────────

memory = MemoryManager()
vector_memory = VectorMemoryManager()
srs = SpacedRepetitionEngine()

# ── Tool definitions (OpenAI function-calling schema) ───────────────────

STUDENT_ID_SCHEMA = {
    "type": "string",
    "description": "Student profile scope injected by the UI/session. Use the provided value; do not invent one.",
    "default": DEFAULT_STUDENT_ID,
}

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "save_study_session",
            "description": "Prompt step: save a completed study session to memory, including full study notes for semantic recall later.",
            "parameters": {
                "type": "object",
                "properties": {
                    "student_id": STUDENT_ID_SCHEMA,
                    "topic": {"type": "string", "description": "The subject or topic studied"},
                    "concepts_learned": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of specific concepts covered in this session",
                    },
                    "session_text": {
                        "type": "string",
                        "description": "The actual study notes/content, used for semantic embedding",
                    },
                    "difficulty_rating": {
                        "type": "integer",
                        "description": "How difficult was this session (1-5)?",
                        "default": 3,
                    },
                    "notes": {"type": "string", "description": "Additional notes", "default": ""},
                },
                "required": ["topic", "concepts_learned", "session_text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_study_history",
            "description": "Retrieve the current student's past study sessions, combining exact topic matches with semantically related notes.",
            "parameters": {
                "type": "object",
                "properties": {
                    "student_id": STUDENT_ID_SCHEMA,
                    "topic": {"type": "string", "description": "Filter by topic name", "default": None},
                    "semantic_query": {
                        "type": "string",
                        "description": "Free-text description of what to search for by meaning",
                        "default": None,
                    },
                    "limit": {"type": "integer", "description": "Max results to return", "default": 10},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_quiz",
            "description": "Practice step: generate quiz questions based on the current student's actual study history for a topic.",
            "parameters": {
                "type": "object",
                "properties": {
                    "student_id": STUDENT_ID_SCHEMA,
                    "topic": {"type": "string", "description": "The topic to generate questions about"},
                    "num_questions": {
                        "type": "integer",
                        "description": "How many questions to generate (3-10)?",
                        "default": 5,
                    },
                    "difficulty": {
                        "type": "string",
                        "enum": ["easy", "medium", "hard"],
                        "description": "Difficulty level of questions",
                        "default": "medium",
                    },
                },
                "required": ["topic"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_weak_areas",
            "description": "Retry step: identify the current student's concepts needing urgent review, combining low mastery with due dates.",
            "parameters": {"type": "object", "properties": {"student_id": STUDENT_ID_SCHEMA}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_study_plan",
            "description": "Create a personalized study plan prioritizing the current student's weak and overdue concepts.",
            "parameters": {
                "type": "object",
                "properties": {
                    "student_id": STUDENT_ID_SCHEMA,
                    "goal": {"type": "string", "description": "The learning goal or objective"},
                    "days_available": {
                        "type": "integer",
                        "description": "How many days are available for studying?",
                    },
                    "hours_per_day": {
                        "type": "number",
                        "description": "Hours available per day for study",
                        "default": 2.0,
                    },
                },
                "required": ["goal", "days_available"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "record_quiz_answer",
            "description": "Feedback step: record a quiz answer, update mastery level, and return whether the student should retry.",
            "parameters": {
                "type": "object",
                "properties": {
                    "student_id": STUDENT_ID_SCHEMA,
                    "topic": {"type": "string", "description": "The topic/concept being tested"},
                    "question": {"type": "string", "description": "The quiz question text"},
                    "correct_answer": {"type": "string", "description": "The correct answer"},
                    "student_answer": {"type": "string", "description": "The student's answer"},
                    "is_correct": {"type": "boolean", "description": "Was the answer correct?"},
                },
                "required": ["topic", "question", "correct_answer", "student_answer", "is_correct"],
            },
        },
    },
]


def _normalize_student_id(student_id=None) -> str:
    cleaned = str(student_id or DEFAULT_STUDENT_ID).strip()
    return cleaned or DEFAULT_STUDENT_ID


# ── Helper: get combined weak areas (reused by get_weak_areas and create_study_plan) ──

def _get_priority_concepts(student_id=DEFAULT_STUDENT_ID) -> list:
    """Combine low-mastery and overdue concepts into a ranked scoped priority list."""
    student_id = _normalize_student_id(student_id)
    weak_result = memory.get_weak_areas(limit=10, student_id=student_id)
    due_result = srs.get_due_concepts(student_id=student_id)

    weak_areas = weak_result.get("weak_areas", []) if weak_result.get("success") else []
    due_concepts = due_result.get("due", []) if due_result.get("success") else []

    weak_names = {w["concept_name"] for w in weak_areas}
    due_names = {d["concept_name"] for d in due_concepts}

    both = weak_names & due_names
    priority = [name for name in [w["concept_name"] for w in weak_areas] if name in both]

    overdue_only = [d["concept_name"] for d in due_concepts if d["concept_name"] not in weak_names]
    priority.extend(overdue_only)

    weak_only = [w["concept_name"] for w in weak_areas if w["concept_name"] not in due_names]
    priority.extend(weak_only)

    return priority


# ── Main dispatcher ─────────────────────────────────────────────────────

def execute_tool(tool_name: str, tool_arguments: dict, student_id: str = DEFAULT_STUDENT_ID) -> str:
    """Execute a tool by name and return the result as a JSON string."""
    try:
        tool_arguments = tool_arguments or {}
        student_id = _normalize_student_id(tool_arguments.get("student_id") or student_id)
        tool_arguments["student_id"] = student_id

        if tool_name == "save_study_session":
            topic = tool_arguments.get("topic", "")
            concepts_learned = tool_arguments.get("concepts_learned", [])
            session_text = tool_arguments.get("session_text", "")
            difficulty_rating = tool_arguments.get("difficulty_rating", 3)
            notes = tool_arguments.get("notes", "")

            session_result = memory.save_study_session(
                topic=topic,
                concepts_learned=concepts_learned,
                difficulty_rating=difficulty_rating,
                notes=notes,
                student_id=student_id,
            )

            note_result = vector_memory.add_note(
                session_id=str(uuid4()),
                topic=topic,
                concepts=concepts_learned,
                text=session_text,
                student_id=student_id,
            )

            schedules_initialized = 0
            for concept in concepts_learned:
                try:
                    srs.initialize_new_concept_schedule(concept, student_id=student_id)
                    schedules_initialized += 1
                except Exception:
                    pass

            result = {
                "success": True,
                "student_id": student_id,
                "session_saved": session_result,
                "note_embedded": note_result,
                "schedules_initialized": schedules_initialized,
            }

        elif tool_name == "get_study_history":
            topic = tool_arguments.get("topic")
            semantic_query = tool_arguments.get("semantic_query")
            limit = tool_arguments.get("limit", 10)

            structured_results = memory.get_study_history(topic=topic, limit=limit, student_id=student_id)

            semantic_results = {}
            if semantic_query:
                semantic_results = vector_memory.semantic_search(semantic_query, n_results=limit, student_id=student_id)

            result = {
                "student_id": student_id,
                "structured_results": structured_results,
                "semantic_results": semantic_results,
            }

        elif tool_name == "generate_quiz":
            topic = tool_arguments.get("topic", "")
            num_questions = tool_arguments.get("num_questions", 5)
            difficulty = tool_arguments.get("difficulty", "medium")

            history_result = memory.get_study_history(topic=topic, limit=10, student_id=student_id)
            history_summary = ""
            if history_result.get("success"):
                sessions = history_result.get("sessions", [])
                if sessions:
                    session_texts = [
                        f"Session {s.get('session_date')}: {s.get('notes', '')}"
                        for s in sessions[:3]
                    ]
                    history_summary = "\n".join(session_texts)

            semantic_result = vector_memory.semantic_search(topic, n_results=5, student_id=student_id)
            semantic_summary = ""
            if semantic_result.get("success"):
                notes = semantic_result.get("results", [])
                if notes:
                    note_texts = [n.get("text", "")[:100] for n in notes[:3]]
                    semantic_summary = "\n".join(note_texts)

            system_prompt = (
                "You are an expert quiz generator. Create practice questions based on the "
                "student's study history. Respond with ONLY a JSON array, no markdown fences, "
                "no explanation. Each element must be an object with exactly these keys: "
                '"question" (string), "answer" (string), "concept" (string — the specific '
                "concept being tested)."
            )

            user_prompt = f"""Generate {num_questions} {difficulty} quiz questions about "{topic}".

Study history context:
{history_summary}

Related study notes:
{semantic_summary}

Create questions that test actual understanding of what this student studied, not generic trivia.
Respond with ONLY a JSON array, no markdown fences."""

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]

            llm_result = safe_generate(messages=messages, force_tier="complex")

            if not llm_result.get("success"):
                result = {
                    "success": False,
                    "student_id": student_id,
                    "error": "quiz generation failed",
                    "details": llm_result,
                }
            else:
                response_text = llm_result.get("text", "")
                try:
                    questions = json.loads(response_text)
                except json.JSONDecodeError:
                    cleaned = response_text.strip()
                    if cleaned.startswith("```"):
                        cleaned = cleaned.split("\n", 1)[-1]
                    if cleaned.endswith("```"):
                        cleaned = cleaned.rsplit("```", 1)[0]
                    cleaned = cleaned.strip()

                    try:
                        questions = json.loads(cleaned)
                    except json.JSONDecodeError:
                        result = {
                            "success": False,
                            "student_id": student_id,
                            "error": "quiz generation returned unparseable format",
                            "raw_response": response_text,
                        }
                        return json.dumps(result)

                result = {"success": True, "student_id": student_id, "questions": questions, "topic": topic}

        elif tool_name == "get_weak_areas":
            weak_result = memory.get_weak_areas(limit=10, student_id=student_id)
            due_result = srs.get_due_concepts(student_id=student_id)
            priority = _get_priority_concepts(student_id=student_id)

            result = {
                "success": True,
                "student_id": student_id,
                "priority_concepts": priority,
                "mastery_based": weak_result,
                "schedule_based": due_result,
            }

        elif tool_name == "create_study_plan":
            goal = tool_arguments.get("goal", "")
            days_available = tool_arguments.get("days_available", 7)
            hours_per_day = tool_arguments.get("hours_per_day", 2.0)

            priority_concepts = _get_priority_concepts(student_id=student_id)
            all_topics = memory.get_all_studied_topics(student_id=student_id)

            system_prompt = (
                "You are an expert study planner. Create a personalized, day-by-day study "
                "plan based on the student's goals, available time, and priority areas. "
                "Format the plan as clear, actionable markdown with specific topics and "
                "time allocations for each day."
            )

            priority_text = (
                ", ".join(priority_concepts[:5])
                if priority_concepts
                else "no specific priority areas identified"
            )
            topics_text = ", ".join(all_topics) if all_topics else "no topics studied yet"

            user_prompt = f"""Create a {days_available}-day study plan for the goal: "{goal}"

Available time: {hours_per_day} hours per day

Priority concepts for this student (focus more on these): {priority_text}

All topics studied by this student: {topics_text}

Create a day-by-day plan with specific time allocations. Use markdown formatting for clarity."""

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]

            llm_result = safe_generate(messages=messages, force_tier="complex")

            if not llm_result.get("success"):
                result = {
                    "success": False,
                    "student_id": student_id,
                    "error": "study plan generation failed",
                    "details": llm_result,
                }
            else:
                result = {
                    "success": True,
                    "student_id": student_id,
                    "plan_text": llm_result.get("text", ""),
                    "based_on_priority_concepts": priority_concepts,
                }

        elif tool_name == "record_quiz_answer":
            topic = tool_arguments.get("topic", "")
            question = tool_arguments.get("question", "")
            correct_answer = tool_arguments.get("correct_answer", "")
            student_answer = tool_arguments.get("student_answer", "")
            is_correct = tool_arguments.get("is_correct", False)

            quiz_result = memory.save_quiz_result(
                topic=topic,
                question=question,
                correct_answer=correct_answer,
                student_answer=student_answer,
                is_correct=is_correct,
                student_id=student_id,
            )

            schedule_result = srs.process_review(concept_name=topic, is_correct=is_correct, student_id=student_id)
            concept = memory.get_concept(topic, student_id=student_id)
            due_result = srs.get_due_concepts(student_id=student_id)
            weak_result = memory.get_weak_areas(limit=10, student_id=student_id)

            mastery_level = concept.get("mastery_level") if "error" not in concept else None
            due_names = {item.get("concept_name") for item in due_result.get("due", [])} if due_result.get("success") else set()
            weak_names = {item.get("concept_name") for item in weak_result.get("weak_areas", [])} if weak_result.get("success") else set()
            retry_recommended = (mastery_level is not None and mastery_level < 4) or topic in due_names or topic in weak_names or not is_correct

            result = {
                "success": True,
                "student_id": student_id,
                "quiz_saved": quiz_result,
                "schedule_updated": schedule_result,
                "feedback": {
                    "is_correct": bool(is_correct),
                    "mastery_level": mastery_level,
                    "retry_recommended": retry_recommended,
                    "message": (
                        f"Correct. Mastery for {topic} is now {mastery_level}/10."
                        if is_correct
                        else f"Not yet. Mastery for {topic} is now {mastery_level}/10, so retry is recommended."
                    ),
                },
            }

        else:
            result = {"error": f"Unknown tool: {tool_name}"}

    except Exception as e:
        result = {"error": f"Tool execution failed: {str(e)}"}

    return json.dumps(result)
