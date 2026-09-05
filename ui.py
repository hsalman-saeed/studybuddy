"""Gradio web interface with auth gate, guided Learning Loop, and education features."""

import json
import re

import gradio as gr

from auth import signup, login
from agent import StudyBuddyAgent
from memory_sqlite import DEFAULT_STUDENT_ID, MemoryManager
from tools import execute_tool
from visualizations import (
    create_mastery_snapshot_chart,
    create_accuracy_trend_chart,
    create_urgency_heatmap,
    create_streak_chart,
    get_dashboard_summary,
)

# ── Module-level read-only stats accessor ───────────────────────────────

stats_memory = MemoryManager()


# ── Helper functions ────────────────────────────────────────────────────

def normalize_student_id(student_id):
    """Return the current student profile scope."""
    cleaned = str(student_id or DEFAULT_STUDENT_ID).strip()
    return cleaned or DEFAULT_STUDENT_ID


def parse_concepts(concepts_text):
    """Split comma/newline concept input into a clean concept list."""
    parts = re.split(r"[,\n]", concepts_text or "")
    return [p.strip() for p in parts if p.strip()]


def create_new_agent(student_id=DEFAULT_STUDENT_ID):
    """Return a fresh StudyBuddyAgent for this browser session."""
    return StudyBuddyAgent(student_id=normalize_student_id(student_id))


def ensure_agent(agent_state, student_id):
    """Create or replace the agent when the selected student profile changes."""
    current_student_id = normalize_student_id(student_id)
    if agent_state is None or getattr(agent_state, "student_id", None) != current_student_id:
        agent_state = create_new_agent(current_student_id)
    return agent_state


def get_greeting_and_stats(student_id=DEFAULT_STUDENT_ID):
    """Build a greeting message based on scoped study history."""
    student_id = normalize_student_id(student_id)
    stats = stats_memory.get_overall_stats(student_id=student_id)
    topics = stats_memory.get_all_studied_topics(student_id=student_id)

    total_sessions = stats.get("total_sessions", 0)

    if total_sessions == 0:
        return (
            f"Welcome to StudyBuddy, **{student_id}**! I'm your AI study assistant with "
            "persistent memory. Use the guided Prompt → Practice → Feedback → Retry loop, "
            "or chat naturally and I will save sessions, quiz you, identify weak areas, "
            "and build study plans for this profile only."
        )

    accuracy = stats.get("overall_accuracy", 0.0)
    topic_count = len(topics)
    return (
        f"Welcome back, **{student_id}**! You've completed **{total_sessions}** study session(s) "
        f"across **{topic_count}** topic(s) with an overall quiz accuracy of "
        f"**{accuracy}%**. What would you like to work on today?"
    )


def load_profile(student_id):
    """Initialize the selected student profile across chat, stats, and dashboard."""
    student_id = normalize_student_id(student_id)
    agent = create_new_agent(student_id)
    chat_history = [{"role": "assistant", "content": get_greeting_and_stats(student_id)}]
    return (agent, None, chat_history, refresh_stats_display(student_id), *refresh_dashboard(student_id))


def respond(message, chat_history, agent_state, student_id, tutor_mode):
    """Process a user message through the agent and return the updated chat."""
    if not message or not message.strip():
        return chat_history, "", ensure_agent(agent_state, student_id)

    actual_message = message
    if tutor_mode:
        actual_message = f"Explain this step by step like a patient tutor: {message}"

    agent_state = ensure_agent(agent_state, student_id)
    response = agent_state.chat(actual_message)

    chat_history = chat_history or []
    chat_history.append({"role": "user", "content": message})
    chat_history.append({"role": "assistant", "content": response})

    return chat_history, "", agent_state


def handle_new_session(agent_state, student_id):
    """Reset the conversation and return a fresh chat view for the active student."""
    agent_state = ensure_agent(agent_state, student_id)
    confirmation = agent_state.reset_session()
    chat_history = [{"role": "assistant", "content": confirmation}]
    return chat_history, agent_state


def refresh_stats_display(student_id=DEFAULT_STUDENT_ID):
    """Read scoped stats and format as Markdown."""
    student_id = normalize_student_id(student_id)
    stats = stats_memory.get_overall_stats(student_id=student_id)
    topics = stats_memory.get_all_studied_topics(student_id=student_id)

    total_sessions = stats.get("total_sessions", 0)
    total_topics = stats.get("total_topics", 0)
    total_quiz = stats.get("total_quiz_questions", 0)
    accuracy = stats.get("overall_accuracy", 0.0)

    lines = [
        f"**Student profile:** `{student_id}`",
        f"**Total study sessions:** {total_sessions}",
        f"**Topics studied:** {total_topics}",
        f"**Quiz questions attempted:** {total_quiz}",
        f"**Overall accuracy:** {accuracy}%",
        "",
        "**Topics:**",
    ]

    if topics:
        for t in topics:
            lines.append(f"- {t}")
    else:
        lines.append("- *No topics yet — start studying!*")

    return "\n".join(lines)


def refresh_dashboard(student_id=DEFAULT_STUDENT_ID):
    """Build scoped dashboard summary and all 4 chart figures."""
    student_id = normalize_student_id(student_id)
    summary = get_dashboard_summary(student_id=student_id)
    total_sessions = summary.get("total_sessions", 0)
    total_topics = summary.get("total_topics", 0)
    accuracy = summary.get("overall_accuracy", 0.0)
    current_streak = summary.get("current_streak", 0)

    summary_md = (
        f"**Student:** `{student_id}` | "
        f"**{total_sessions} sessions** across **{total_topics} topics** | "
        f"**{accuracy}% quiz accuracy** | "
        f"**{current_streak}-day** study streak"
    )

    mastery_fig = create_mastery_snapshot_chart(student_id=student_id)
    accuracy_fig = create_accuracy_trend_chart(student_id=student_id)
    urgency_fig = create_urgency_heatmap(student_id=student_id)
    streak_fig = create_streak_chart(student_id=student_id)

    return summary_md, mastery_fig, accuracy_fig, urgency_fig, streak_fig


def prompt_step(student_id, topic, concepts_text, session_text, difficulty_rating):
    """Step 1: save the student's prompt/study session."""
    student_id = normalize_student_id(student_id)
    concepts = parse_concepts(concepts_text)
    if not topic or not topic.strip() or not concepts or not session_text or not session_text.strip():
        return "Fill in a topic, at least one concept, and what you studied to complete Prompt."

    result = json.loads(execute_tool(
        "save_study_session",
        {
            "student_id": student_id,
            "topic": topic.strip(),
            "concepts_learned": concepts,
            "session_text": session_text.strip(),
            "difficulty_rating": int(difficulty_rating or 3),
            "notes": session_text.strip(),
        },
        student_id=student_id,
    ))
    saved = result.get("session_saved", {})
    if not saved.get("success"):
        return f"Prompt could not be saved: {saved.get('error', result)}"
    return (
        f"Prompt complete for `{student_id}`. Saved **{topic.strip()}** with "
        f"{len(concepts)} concept(s): {', '.join(concepts)}. Next: Practice."
    )


def practice_step(student_id, topic, num_questions, difficulty):
    """Step 2: generate a quiz and store the first active question in state."""
    student_id = normalize_student_id(student_id)
    if not topic or not topic.strip():
        return "Enter a topic to practice.", None

    history = stats_memory.get_study_history(student_id=student_id)
    if not history.get("sessions"):
        return (
            f"No study sessions found yet for `{student_id}`. "
            "Please complete **Step 1: Prompt** first and log what you studied "
            "before generating Practice questions.",
            None,
        )

    result = json.loads(execute_tool(
        "generate_quiz",
        {
            "student_id": student_id,
            "topic": topic.strip(),
            "num_questions": int(num_questions or 3),
            "difficulty": difficulty or "medium",
        },
        student_id=student_id,
    ))
    if not result.get("success"):
        return f"Practice quiz could not be generated: {result.get('error', result)}", None

    questions = result.get("questions", [])
    if not questions:
        return "Practice quiz returned no questions. Try another topic.", None

    first = questions[0]
    quiz_state = {
        "student_id": student_id,
        "topic": first.get("concept") or result.get("topic") or topic.strip(),
        "question": first.get("question", ""),
        "correct_answer": first.get("answer", ""),
        "all_questions": questions,
    }
    quiz_md = (
        "Practice ready. Answer this question, then submit it under Feedback.\n\n"
        f"**Question:** {quiz_state['question']}"
    )
    return quiz_md, quiz_state


def feedback_step(student_id, quiz_state, student_answer):
    """Step 3: record an answer and show explicit mastery feedback."""
    student_id = normalize_student_id(student_id)
    if not quiz_state:
        return (
            "No active Practice question found. Please complete **Step 2: Practice** first, "
            "then come back to Feedback.",
            "Retry decision will appear after Feedback.",
        )
    if not student_answer or not student_answer.strip():
        return "Enter your answer before requesting Feedback.", "Retry decision will appear after Feedback."

    correct_answer = quiz_state.get("correct_answer", "")
    normalized_answer = student_answer.strip().lower()
    normalized_correct = correct_answer.strip().lower()
    is_correct = bool(normalized_answer) and (
        normalized_answer == normalized_correct
        or normalized_answer in normalized_correct
        or normalized_correct in normalized_answer
    )

    result = json.loads(execute_tool(
        "record_quiz_answer",
        {
            "student_id": student_id,
            "topic": quiz_state.get("topic", ""),
            "question": quiz_state.get("question", ""),
            "correct_answer": correct_answer,
            "student_answer": student_answer.strip(),
            "is_correct": is_correct,
        },
        student_id=student_id,
    ))
    feedback = result.get("feedback", {})
    mastery = feedback.get("mastery_level", "unknown")
    retry_recommended = feedback.get("retry_recommended", False)
    status = "Correct" if feedback.get("is_correct") else "Not correct yet"

    feedback_md = (
        f"Feedback: **{status}.**\n\n"
        f"Correct answer: {correct_answer}\n\n"
        f"Updated mastery for **{quiz_state.get('topic', '')}**: **{mastery}/10**."
    )
    retry_md = build_retry_message(student_id, retry_recommended, quiz_state.get("topic", ""))
    return feedback_md, retry_md


def build_retry_message(student_id, retry_recommended, topic):
    """Step 4: decide whether to explicitly prompt another attempt."""
    weak = stats_memory.get_weak_areas(limit=5, student_id=student_id).get("weak_areas", [])
    due = stats_memory.get_concepts_due_for_review(student_id=student_id).get("due", [])
    weak_names = [item.get("concept_name") for item in weak]
    due_names = [item.get("concept_name") for item in due]

    if retry_recommended:
        reasons = []
        if topic in weak_names:
            reasons.append("low mastery")
        if topic in due_names:
            reasons.append("due for review")
        if not reasons:
            reasons.append("this answer needs reinforcement")
        return (
            f"Retry: **Try another question on {topic}.** Reason: {', '.join(reasons)}. "
            "Use Practice again or ask the chat for a follow-up quiz."
        )

    if weak_names or due_names:
        targets = ", ".join((due_names + weak_names)[:3])
        return f"Retry: Your answer is stable here. Next best retry target: **{targets}**."

    return "Retry: No urgent retry is due right now. Keep practicing to strengthen retention."


# ── Auth handlers ────────────────────────────────────────────────────────

# Return tuple indices for successful login:
#  0: login_form (visible=False)
#  1: app_column (visible=True)
#  2: user_display_md
#  3: student_id_state
#  4: agent_state
#  5: quiz_state
#  6: chatbot
#  7: stats_display
#  8: dashboard_summary_md
#  9: mastery_plot
# 10: accuracy_plot
# 11: urgency_plot
# 12: streak_plot
# 13: auth_status_msg
# 14: stored_username (BrowserState — persists across page refreshes)


def _auth_fail(message):
    """No-op auth outputs; only the status message is set."""
    return (gr.update(),) * 13 + (message, gr.update())


def handle_login(username, password):
    success, student_id, message = login(username, password)
    if success:
        agent, quiz_st, chat, stats, dash_summary, m_plot, a_plot, u_plot, s_plot = load_profile(student_id)
        return (
            gr.update(visible=False),   # hide login form
            gr.update(visible=True),    # show app
            f"**{student_id}**",        # user display
            student_id,                 # student_id state
            agent, quiz_st, chat, stats, dash_summary,
            m_plot, a_plot, u_plot, s_plot,
            "",                         # clear status
            {"username": student_id},   # persist username in BrowserState
        )
    return _auth_fail(message)


def handle_signup(username, password, confirm):
    success, message = signup(username, password, confirm)
    if success:
        return handle_login(username, password)
    return _auth_fail(message)


def handle_demo_login():
    return handle_login("demo_student", "demo123")


def handle_logout():
    return (
        gr.update(visible=True),    # show login
        gr.update(visible=False),   # hide app
        "",                         # clear user display
        "",                         # clear student_id state
        {"username": ""},           # clear stored username (BrowserState)
    )


def _stored_username_of(stored_user):
    """Extract the username from the BrowserState payload (dict or plain str)."""
    if isinstance(stored_user, dict):
        return str(stored_user.get("username") or "").strip()
    return str(stored_user or "").strip()


def auto_login_from_storage(stored_user):
    """Restore the logged-in profile on page refresh from browser localStorage."""
    username = _stored_username_of(stored_user)
    if username and stats_memory.user_exists(username):
        agent, quiz_st, chat, stats, dash_summary, m_plot, a_plot, u_plot, s_plot = load_profile(username)
        return (
            gr.update(visible=False),  # hide login form
            gr.update(visible=True),   # show app
            f"**{username}**",         # user display
            username,                  # student_id state
            agent, quiz_st, chat, stats, dash_summary,
            m_plot, a_plot, u_plot, s_plot,
            {"username": username},    # keep stored username
        )
    # No valid stored session — leave the login form up and clear stale data
    return (
        gr.update(), gr.update(), gr.update(), gr.update(), gr.update(),
        gr.update(), gr.update(), gr.update(), gr.update(), gr.update(),
        gr.update(), gr.update(), gr.update(),
        {"username": ""},
    )


# ── Learning Loop progress tracking ─────────────────────────────────────

def update_progress_after_prompt(status_text, progress):
    progress = progress or {"prompt_done": False, "practice_done": False, "feedback_done": False}
    if "Prompt complete" in str(status_text):
        progress["prompt_done"] = True
        indicator = "**Step 1** ✅ → **Step 2: Practice** → Step 3 → Step 4"
    else:
        indicator = "**Step 1: Prompt** (fill in and save) → Step 2 → Step 3 → Step 4"
    return indicator, progress


def update_progress_after_practice(practice_text, quiz_state, progress):
    progress = progress or {"prompt_done": False, "practice_done": False, "feedback_done": False}
    if quiz_state is not None:
        progress["practice_done"] = True
        indicator = "Step 1 ✅ → **Step 2** ✅ → **Step 3: Feedback** → Step 4"
    else:
        indicator = "Step 1 ✅ → **Step 2: Practice** (generate quiz) → Step 3 → Step 4"
    return indicator, progress


def update_progress_after_feedback(feedback_text, retry_text, progress):
    progress = progress or {"prompt_done": False, "practice_done": False, "feedback_done": False}
    progress["feedback_done"] = True
    indicator = "Step 1 ✅ → Step 2 ✅ → **Step 3** ✅ → **Step 4: Review Retry**"
    return indicator, progress


# ── Personalized practice handlers ────────────────────────────────────────

def get_weak_area_topic(student_id):
    student_id = normalize_student_id(student_id)
    weak = stats_memory.get_weak_areas(limit=1, student_id=student_id).get("weak_areas", [])
    if weak:
        return weak[0].get("concept_name", "")
    return ""


def get_due_review_topic(student_id):
    student_id = normalize_student_id(student_id)
    due = stats_memory.get_concepts_due_for_review(student_id=student_id).get("due", [])
    if due:
        return due[0].get("concept_name", "")
    return ""


# ── Learning Paths handler ────────────────────────────────────────────────

def generate_learning_path(student_id, goal):
    student_id = normalize_student_id(student_id)
    if not goal or not goal.strip():
        return "Please enter a learning goal to generate your personalized learning path."

    result = json.loads(execute_tool(
        "create_study_plan",
        {"student_id": student_id, "goal": goal.strip(), "days_available": 14},
        student_id=student_id,
    ))
    if not result.get("success"):
        return f"Could not generate learning path: {result.get('error', 'Unknown error')}"
    plan_text = result.get("plan_text") or result.get("plan") or str(result)

    # Save the generated path
    stats_memory.save_learning_path(student_id, goal.strip(), plan_text)

    return plan_text


def _show_generating():
    """Instant loading indicator shown while the LLM generates the path."""
    return "⏳ **Generating your personalized learning path...** This may take a moment."


def _load_saved_paths(student_id):
    """Render the student's saved learning paths, newest first."""
    student_id = normalize_student_id(student_id)
    paths = stats_memory.get_learning_paths(student_id, limit=10)
    if not paths:
        return "No saved learning paths yet. Generate one above!"
    lines = []
    for p in paths:
        lines.append(f"---\n**Goal:** {p['goal']}\n**Created:** {p['created_at']}\n\n{p['plan_text']}\n")
    return "\n".join(lines)


# ── Assessment handler ────────────────────────────────────────────────────

def get_assessment_table(student_id):
    student_id = normalize_student_id(student_id)
    concepts = stats_memory.get_all_concepts_with_details(student_id=student_id)
    if not concepts:
        return "No concepts studied yet. Complete some study sessions to see your assessment."

    lines = ["| Concept | Mastery | Correct | Wrong | Next Review |", "|---|---|---|---|---|"]
    for c in concepts:
        lines.append(
            f"| {c['concept_name']} | {c['mastery_level']}/10 | {c.get('times_correct', 0)} | "
            f"{c.get('times_wrong', 0)} | {c.get('next_review_date', 'N/A')} |"
        )
    return "\n".join(lines)


# ── CSS ────────────────────────────────────────────────────────────────────

APP_CSS = """
html, body { margin: 0; }
.gradio-container {
    min-height: 100vh;
    padding: 6px 14px !important;
    box-sizing: border-box;
}
.gradio-container, .gradio-container * { max-width: 100%; box-sizing: border-box; }

/* Login card */
.login-card { max-width: 420px; margin: 8vh auto !important; }
.login-card .block { padding: 8px !important; }

/* Compact header */
#app-header { flex-shrink: 0 !important; padding: 4px 0 !important; }
#app-header h3 { margin: 0 !important; font-size: 1rem !important; }

/* Tabs fill remaining space.
   NOTE: never force `display` on `#tabs-wrap > div` or `.tabitem` — Gradio
   hides inactive tab panels via an inline `display: none`, so a
   `display: flex !important` here would render every tab's content at once. */
#tabs-wrap {
    flex: 1 1 auto !important; min-height: 0 !important;
    overflow: hidden !important;
}

/* Internal scroll containers */
.app-scroll {
    flex: 1 1 auto !important; min-height: 0 !important;
    overflow-y: auto !important; overflow-x: hidden !important;
    padding-right: 4px;
}

/* Chatbot fills space */
#main-chatbot { flex: 1 1 auto !important; min-height: 200px !important; }

/* Step notices */
.step-notice { background: #e8f4fd; border-left: 4px solid #2196F3; padding: 6px 10px; margin: 4px 0 8px 0; border-radius: 4px; font-size: 0.85rem; }
.step-complete { background: #e8f5e9; border-left: 4px solid #4CAF50; }
.step-warning { background: #fff3e0; border-left: 4px solid #FF9800; }

/* Dashboard plots constrained */
.dash-plot { max-height: 45vh; overflow: hidden; }

/* Progress indicator */
.progress-bar { background: #f5f5f5; padding: 8px 12px; border-radius: 6px; margin-bottom: 8px; text-align: center; font-size: 0.9rem; }

@media (max-width: 900px) {
    .login-card { max-width: 95%; margin: 4vh auto !important; }
    .app-scroll .row, .app-scroll .gr-row { flex-direction: column !important; }
}
"""


# ── Build the interface ────────────────────────────────────────────────────

def _build_demo():
    with gr.Blocks(
        title="StudyBuddy",
        fill_height=True,
    ) as demo:

        # ── State variables ──
        agent_state = gr.State(value=None)
        quiz_state = gr.State(value=None)
        student_id_state = gr.State(value="")
        loop_progress = gr.State(value={"prompt_done": False, "practice_done": False, "feedback_done": False})

        # Browser-persistent state: survives page refreshes via localStorage.
        # Stored as a dict because Gradio skips writing falsy values, so a
        # bare "" could never overwrite (clear) a previously stored username.
        stored_username = gr.BrowserState(default_value={"username": ""})

        # ════════════════════════════════════════════════════════════════
        # AUTH GATE — Login / Signup form (visible by default)
        # ════════════════════════════════════════════════════════════════
        with gr.Column(visible=True, elem_classes=["login-card"]) as login_form:
            gr.Markdown("# StudyBuddy\n**AI Study Assistant with Persistent Memory**")
            auth_username = gr.Textbox(label="Username", placeholder="Enter your username")
            auth_password = gr.Textbox(label="Password", placeholder="Enter your password", type="password")
            auth_confirm = gr.Textbox(label="Confirm Password (sign up only)", placeholder="Confirm password", type="password")

            with gr.Row():
                login_btn = gr.Button("Login", variant="primary", scale=1)
                signup_btn = gr.Button("Sign Up", variant="secondary", scale=1)
            demo_login_btn = gr.Button("Demo Login (quick access)", variant="secondary", size="sm")
            auth_status = gr.Markdown(value="", elem_classes=["step-notice"])

        # ════════════════════════════════════════════════════════════════
        # MAIN APP — hidden until login succeeds
        # ════════════════════════════════════════════════════════════════
        with gr.Column(visible=False) as app_column:

            # ── Slim header ──
            with gr.Row(elem_id="app-header"):
                gr.Markdown("**StudyBuddy**", elem_id="app-title", scale=2)
                user_display_md = gr.Markdown(value="", scale=2)
                logout_btn = gr.Button("Logout", variant="secondary", size="sm", scale=0)

            # ── Tabs ──
            with gr.Column(elem_id="tabs-wrap", scale=1):
                with gr.Tabs():

                    # ════════════════════════════════════════════
                    # TAB: Learning Loop
                    # ════════════════════════════════════════════
                    with gr.Tab("Learning Loop"):
                        with gr.Column(elem_classes=["app-scroll"]):
                            progress_indicator = gr.Markdown(
                                value="**Step 1: Prompt** (fill in and save) → Step 2 → Step 3 → Step 4",
                                elem_classes=["progress-bar"],
                            )

                            # Step 1: Prompt (open by default)
                            with gr.Accordion("Step 1: Prompt — Log what you studied", open=True):
                                gr.Markdown(
                                    "💡 *Log a study session: enter your topic, concepts, and notes. "
                                    "This is the foundation for Practice and Feedback.*",
                                    elem_classes=["step-notice"],
                                )
                                loop_topic = gr.Textbox(label="What did you study?", placeholder="Python Functions")
                                loop_concepts = gr.Textbox(label="Concepts covered", placeholder="parameters, return values, scope")
                                loop_notes = gr.Textbox(label="Describe what you learned", lines=3)
                                loop_difficulty = gr.Slider(1, 5, value=3, step=1, label="Difficulty")
                                save_prompt_btn = gr.Button("Save Prompt", variant="primary")
                                prompt_status = gr.Markdown("Prompt status will appear here.")

                            # Step 2: Practice
                            with gr.Accordion("Step 2: Practice — Get quiz questions", open=False):
                                gr.Markdown(
                                    "💡 *Generate a quiz question on your topic. "
                                    "You need to complete Step 1 first.*",
                                    elem_classes=["step-notice"],
                                )
                                practice_topic = gr.Textbox(label="Topic to quiz", placeholder="scope")
                                with gr.Row():
                                    practice_count = gr.Slider(1, 5, value=1, step=1, label="Number of questions", scale=2)
                                    practice_difficulty = gr.Dropdown(["easy", "medium", "hard"], value="medium", label="Difficulty", scale=1)
                                practice_btn = gr.Button("Generate Practice", variant="primary")
                                practice_output = gr.Markdown("Practice question will appear here.")

                                # Personalized Practice section
                                gr.Markdown("---\n**Personalized Practice**")
                                with gr.Row():
                                    weak_area_btn = gr.Button("Practice Weak Areas", variant="secondary", size="sm")
                                    due_review_btn = gr.Button("Due for Review", variant="secondary", size="sm")

                            # Step 3: Feedback
                            with gr.Accordion("Step 3: Feedback — Check your answer", open=False):
                                gr.Markdown(
                                    "💡 *Enter your answer to the quiz question from Step 2. "
                                    "You'll see whether you were correct and your updated mastery level.*",
                                    elem_classes=["step-notice"],
                                )
                                answer_input = gr.Textbox(label="Your answer", lines=2)
                                feedback_btn = gr.Button("Record Answer + Show Feedback", variant="primary")
                                feedback_output = gr.Markdown("Feedback will show correctness and updated mastery.")

                            # Step 4: Retry
                            with gr.Accordion("Step 4: Retry — Review and retry", open=False):
                                gr.Markdown(
                                    "💡 *Based on your feedback, see whether you should retry "
                                    "or move on to a new topic.*",
                                    elem_classes=["step-notice"],
                                )
                                retry_output = gr.Markdown("Retry guidance will appear after Feedback.")

                    # ════════════════════════════════════════════
                    # TAB: Chat
                    # ════════════════════════════════════════════
                    with gr.Tab("Chat"):
                        with gr.Column(elem_classes=["app-scroll"]):
                            chatbot = gr.Chatbot(
                                elem_id="main-chatbot",
                                placeholder=(
                                    "StudyBuddy can save your study sessions, quiz you on past material, "
                                    "identify weak areas, and create study plans. Just type naturally!"
                                ),
                            )
                            with gr.Row():
                                msg_input = gr.Textbox(
                                    scale=4,
                                    placeholder=(
                                        'Try: "I just studied X" or "Quiz me on Y" or '
                                        '"What should I focus on?"'
                                    ),
                                    show_label=False,
                                )
                                send_btn = gr.Button("Send", scale=1, variant="primary")

                            with gr.Row():
                                new_session_btn = gr.Button("New Session", size="sm")
                                tutor_mode_cb = gr.Checkbox(label="Tutor Mode", value=False, scale=0)

                            with gr.Accordion("Your Learning Stats", open=False):
                                stats_display = gr.Markdown(
                                    value="*Click 'Refresh Stats' to load your learning data.*"
                                )
                                refresh_btn = gr.Button("Refresh Stats", size="sm")

                    # ════════════════════════════════════════════
                    # TAB: Dashboard
                    # ════════════════════════════════════════════
                    with gr.Tab("Dashboard"):
                        with gr.Column(elem_classes=["app-scroll"]):
                            with gr.Row():
                                gr.Markdown("### Your Learning Dashboard", scale=3)
                                refresh_dash_btn = gr.Button("Refresh Dashboard", scale=1, variant="secondary", size="sm")

                            dashboard_summary_md = gr.Markdown(
                                value="*Click 'Refresh Dashboard' to load your learning data.*"
                            )

                            with gr.Row():
                                with gr.Column(scale=1):
                                    mastery_plot = gr.Plot(elem_classes=["dash-plot"])
                                with gr.Column(scale=1):
                                    accuracy_plot = gr.Plot(elem_classes=["dash-plot"])

                            with gr.Row():
                                with gr.Column(scale=1):
                                    urgency_plot = gr.Plot(elem_classes=["dash-plot"])
                                with gr.Column(scale=1):
                                    streak_plot = gr.Plot(elem_classes=["dash-plot"])

                            # Assessment accordion
                            with gr.Accordion("Assessment — Concept Details", open=False):
                                assessment_display = gr.Markdown("Click 'Refresh Assessment' to load.")
                                refresh_assessment_btn = gr.Button("Refresh Assessment", size="sm")

                    # ════════════════════════════════════════════
                    # TAB: Learning Paths
                    # ════════════════════════════════════════════
                    with gr.Tab("Learning Paths"):
                        with gr.Column(elem_classes=["app-scroll"]):
                            gr.Markdown(
                                "### Generate a Personalized Learning Path\n"
                                "Enter your learning goal and StudyBuddy will create a "
                                "14-day study plan tailored to your weak areas and schedule."
                            )
                            goal_input = gr.Textbox(
                                label="Learning Goal",
                                placeholder="e.g., Master Python decorators and generators before my exam",
                                lines=2,
                            )
                            generate_path_btn = gr.Button("Generate Learning Path", variant="primary")
                            learning_path_output = gr.Markdown("Your learning path will appear here.")

                            gr.Markdown("---")
                            gr.Markdown("### Weak Areas Summary")
                            weak_areas_display = gr.Markdown("*Click 'Refresh Weak Areas' to load.*")
                            refresh_weak_btn = gr.Button("Refresh Weak Areas", size="sm")

                            gr.Markdown("---")
                            gr.Markdown("### Saved Learning Paths")
                            saved_paths_display = gr.Markdown("*Click 'Load Saved Paths' to see your previous learning paths.*")
                            load_saved_paths_btn = gr.Button("Load Saved Paths", size="sm")

        # ════════════════════════════════════════════════════════════════
        # EVENT WIRING
        # ════════════════════════════════════════════════════════════════

        # All outputs for auth success (15 total — includes BrowserState):
        _auth_outputs = [
            login_form,         # 0
            app_column,         # 1
            user_display_md,    # 2
            student_id_state,   # 3
            agent_state,        # 4
            quiz_state,         # 5
            chatbot,            # 6
            stats_display,      # 7
            dashboard_summary_md,  # 8
            mastery_plot,       # 9
            accuracy_plot,      # 10
            urgency_plot,       # 11
            streak_plot,        # 12
            auth_status,        # 13
            stored_username,    # 14 (BrowserState)
        ]

        # Restore a localStorage-persisted session on page load / refresh.
        # The dependency is captured so a manual login click can cancel a
        # slow in-flight auto-login instead of being overwritten by it.
        initial_load_event = demo.load(
            fn=auto_login_from_storage,
            inputs=[stored_username],
            outputs=[
                login_form, app_column, user_display_md, student_id_state,
                agent_state, quiz_state, chatbot, stats_display, dashboard_summary_md,
                mastery_plot, accuracy_plot, urgency_plot, streak_plot,
                stored_username,
            ],
        )

        login_btn.click(
            fn=handle_login,
            inputs=[auth_username, auth_password],
            outputs=_auth_outputs,
            cancels=[initial_load_event],
        )
        signup_btn.click(
            fn=handle_signup,
            inputs=[auth_username, auth_password, auth_confirm],
            outputs=_auth_outputs,
            cancels=[initial_load_event],
        )
        demo_login_btn.click(
            fn=handle_demo_login,
            inputs=[],
            outputs=_auth_outputs,
            cancels=[initial_load_event],
        )

        logout_btn.click(
            fn=handle_logout,
            inputs=[],
            outputs=[login_form, app_column, user_display_md, student_id_state, stored_username],
        )

        # ── Learning Loop events ──

        save_prompt_btn.click(
            fn=prompt_step,
            inputs=[student_id_state, loop_topic, loop_concepts, loop_notes, loop_difficulty],
            outputs=[prompt_status],
        ).then(
            fn=update_progress_after_prompt,
            inputs=[prompt_status, loop_progress],
            outputs=[progress_indicator, loop_progress],
        )

        practice_btn.click(
            fn=practice_step,
            inputs=[student_id_state, practice_topic, practice_count, practice_difficulty],
            outputs=[practice_output, quiz_state],
        ).then(
            fn=update_progress_after_practice,
            inputs=[practice_output, quiz_state, loop_progress],
            outputs=[progress_indicator, loop_progress],
        )

        # Personalized practice buttons auto-fill the practice topic
        weak_area_btn.click(
            fn=get_weak_area_topic,
            inputs=[student_id_state],
            outputs=[practice_topic],
        )
        due_review_btn.click(
            fn=get_due_review_topic,
            inputs=[student_id_state],
            outputs=[practice_topic],
        )

        feedback_btn.click(
            fn=feedback_step,
            inputs=[student_id_state, quiz_state, answer_input],
            outputs=[feedback_output, retry_output],
        ).then(
            fn=update_progress_after_feedback,
            inputs=[feedback_output, retry_output, loop_progress],
            outputs=[progress_indicator, loop_progress],
        )

        # ── Chat events ──

        for trigger in [send_btn.click, msg_input.submit]:
            trigger(
                fn=respond,
                inputs=[msg_input, chatbot, agent_state, student_id_state, tutor_mode_cb],
                outputs=[chatbot, msg_input, agent_state],
            )

        new_session_btn.click(
            fn=handle_new_session,
            inputs=[agent_state, student_id_state],
            outputs=[chatbot, agent_state],
        )

        refresh_btn.click(
            fn=refresh_stats_display,
            inputs=[student_id_state],
            outputs=[stats_display],
        )

        # ── Dashboard events ──

        refresh_dash_btn.click(
            fn=refresh_dashboard,
            inputs=[student_id_state],
            outputs=[dashboard_summary_md, mastery_plot, accuracy_plot, urgency_plot, streak_plot],
        )

        refresh_assessment_btn.click(
            fn=get_assessment_table,
            inputs=[student_id_state],
            outputs=[assessment_display],
        )

        # ── Learning Paths events ──

        generate_path_btn.click(
            fn=_show_generating,
            inputs=[],
            outputs=[learning_path_output],
        ).then(
            fn=generate_learning_path,
            inputs=[student_id_state, goal_input],
            outputs=[learning_path_output],
        ).then(
            fn=_load_saved_paths,
            inputs=[student_id_state],
            outputs=[saved_paths_display],
        )

        load_saved_paths_btn.click(
            fn=_load_saved_paths,
            inputs=[student_id_state],
            outputs=[saved_paths_display],
        )

        def _refresh_weak_areas(student_id):
            student_id = normalize_student_id(student_id)
            weak = stats_memory.get_weak_areas(limit=10, student_id=student_id).get("weak_areas", [])
            if not weak:
                return "No weak areas identified yet. Complete some study sessions and quizzes first."
            lines = ["| Concept | Mastery | Wrong | Next Review |", "|---|---|---|---|"]
            for w in weak:
                lines.append(
                    f"| {w['concept_name']} | {w['mastery_level']}/10 | "
                    f"{w.get('times_wrong', 0)} | {w.get('next_review_date', 'N/A')} |"
                )
            return "\n".join(lines)

        refresh_weak_btn.click(
            fn=_refresh_weak_areas,
            inputs=[student_id_state],
            outputs=[weak_areas_display],
        )

    return demo


demo = _build_demo()


# ── Launch helper ───────────────────────────────────────────────────────

def launch():
    """Start the Gradio server."""
    demo.launch(
        server_name="127.0.0.1",
        server_port=7860,
        share=False,
        show_error=True,
        css=APP_CSS,
        theme=gr.themes.Soft(),
    )
