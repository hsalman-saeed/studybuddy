"""Gradio web interface that wires agent.py into a usable chat application."""

import gradio as gr

from agent import StudyBuddyAgent
from memory_sqlite import MemoryManager
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

def create_new_agent():
    """Return a fresh StudyBuddyAgent for this browser session."""
    return StudyBuddyAgent()


def get_greeting_and_stats():
    """Build a greeting message based on existing study history."""
    stats = stats_memory.get_overall_stats()
    topics = stats_memory.get_all_studied_topics()

    total_sessions = stats.get("total_sessions", 0)

    if total_sessions == 0:
        return (
            "Welcome to StudyBuddy! I'm your AI study assistant with persistent "
            "memory. Tell me what you've been studying, ask me to quiz you, or "
            "let me help you create a study plan. I'll remember everything across "
            "sessions!"
        )

    accuracy = stats.get("overall_accuracy", 0.0)
    topic_count = len(topics)
    return (
        f"Welcome back! You've completed **{total_sessions}** study session(s) "
        f"across **{topic_count}** topic(s) with an overall quiz accuracy of "
        f"**{accuracy}%**. What would you like to work on today?"
    )


def respond(message, chat_history, agent_state):
    """Process a user message through the agent and return the updated chat."""
    if not message or not message.strip():
        return chat_history, "", agent_state

    # Defensive: create agent if state hasn't been initialized yet (race guard)
    if agent_state is None:
        agent_state = create_new_agent()

    response = agent_state.chat(message)

    chat_history = chat_history or []
    chat_history.append({"role": "user", "content": message})
    chat_history.append({"role": "assistant", "content": response})

    return chat_history, "", agent_state


def handle_new_session(agent_state):
    """Reset the conversation and return a fresh chat view."""
    if agent_state is None:
        agent_state = create_new_agent()
    confirmation = agent_state.reset_session()
    chat_history = [{"role": "assistant", "content": confirmation}]
    return chat_history, agent_state


def refresh_stats_display():
    """Read current stats and format as Markdown."""
    stats = stats_memory.get_overall_stats()
    topics = stats_memory.get_all_studied_topics()

    total_sessions = stats.get("total_sessions", 0)
    total_topics = stats.get("total_topics", 0)
    total_quiz = stats.get("total_quiz_questions", 0)
    accuracy = stats.get("overall_accuracy", 0.0)

    lines = [
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


def refresh_dashboard():
    """Build dashboard summary and all 4 chart figures."""
    summary = get_dashboard_summary()
    total_sessions = summary.get("total_sessions", 0)
    total_topics = summary.get("total_topics", 0)
    accuracy = summary.get("overall_accuracy", 0.0)
    current_streak = summary.get("current_streak", 0)

    summary_md = (
        f"**{total_sessions} sessions** across **{total_topics} topics** | "
        f"**{accuracy}% quiz accuracy** | "
        f"**{current_streak}-day** study streak"
    )

    mastery_fig = create_mastery_snapshot_chart()
    accuracy_fig = create_accuracy_trend_chart()
    urgency_fig = create_urgency_heatmap()
    streak_fig = create_streak_chart()

    return summary_md, mastery_fig, accuracy_fig, urgency_fig, streak_fig


# ── Build the interface ─────────────────────────────────────────────────

def _build_demo():
    with gr.Blocks(title="StudyBuddy") as demo:

        with gr.Tabs():
            # ═══════════════════════════════════════════════════
            # CHAT TAB (existing interface, unchanged internals)
            # ═══════════════════════════════════════════════════
            with gr.Tab("Chat"):

                # Header
                gr.Markdown(
                    "# StudyBuddy — AI Study Assistant with Persistent Memory\n"
                    "Powered by Qwen Cloud · Two-tier memory (SQLite + ChromaDB) · "
                    "Spaced-repetition scheduling"
                )

                # Per-session agent state
                agent_state = gr.State(value=None)

                with gr.Row():
                    # ── Left column: chat ──
                    with gr.Column(scale=2):
                        chatbot = gr.Chatbot(
                            height=500,
                            placeholder=(
                                "StudyBuddy can: save your study sessions, quiz you on "
                                "past material, identify weak areas, and create study "
                                "plans. Just type naturally!"
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

                        new_session_btn = gr.Button("New Session")

                    # ── Right column: stats ──
                    with gr.Column(scale=1):
                        gr.Markdown("### Your Learning Stats")
                        stats_display = gr.Markdown(
                            value="*Click 'Refresh Stats' to load your learning data.*"
                        )
                        refresh_btn = gr.Button("Refresh Stats")

                        gr.Markdown(
                            "### Things you can ask\n"
                            "- **Save a session:** *\"I just studied Python decorators\"*\n"
                            "- **Request a quiz:** *\"Quiz me on decorators\"*\n"
                            "- **Find weak areas:** *\"What should I focus on?\"*\n"
                            "- **Create a plan:** *\"I have an exam in 5 days\"*"
                        )

                # ── Chat tab events ──
                def _on_load():
                    agent = create_new_agent()
                    greeting = get_greeting_and_stats()
                    chat_history = [{"role": "assistant", "content": greeting}]
                    return agent, chat_history

                for trigger in [send_btn.click, msg_input.submit]:
                    trigger(
                        fn=respond,
                        inputs=[msg_input, chatbot, agent_state],
                        outputs=[chatbot, msg_input, agent_state],
                    )

                new_session_btn.click(
                    fn=handle_new_session,
                    inputs=[agent_state],
                    outputs=[chatbot, agent_state],
                )

                refresh_btn.click(
                    fn=refresh_stats_display,
                    inputs=[],
                    outputs=[stats_display],
                )

            # ═══════════════════════════════════════════════════
            # DASHBOARD TAB (new)
            # ═══════════════════════════════════════════════════
            with gr.Tab("Dashboard"):

                with gr.Row():
                    gr.Markdown("### Your Learning Dashboard")
                    refresh_dash_btn = gr.Button("Refresh Dashboard", scale=1, variant="secondary")

                dashboard_summary_md = gr.Markdown(
                    value="*Click 'Refresh Dashboard' to load your learning data.*"
                )

                with gr.Row():
                    with gr.Column(scale=1):
                        mastery_plot = gr.Plot()
                    with gr.Column(scale=1):
                        accuracy_plot = gr.Plot()

                with gr.Row():
                    with gr.Column(scale=1):
                        urgency_plot = gr.Plot()
                    with gr.Column(scale=1):
                        streak_plot = gr.Plot()

                refresh_dash_btn.click(
                    fn=refresh_dashboard,
                    inputs=[],
                    outputs=[
                        dashboard_summary_md,
                        mastery_plot,
                        accuracy_plot,
                        urgency_plot,
                        streak_plot,
                    ],
                )

        # ── Global load events (two independent calls — neither blocks the other) ──
        # Chat greeting fires first and fast so the user sees it immediately
        demo.load(
            fn=_on_load,
            inputs=[],
            outputs=[agent_state, chatbot],
        )

        # Dashboard populates in parallel (chart generation is slower)
        demo.load(
            fn=refresh_dashboard,
            inputs=[],
            outputs=[
                dashboard_summary_md,
                mastery_plot,
                accuracy_plot,
                urgency_plot,
                streak_plot,
            ],
        )

    return demo


demo = _build_demo()


# ── Launch helper ───────────────────────────────────────────────────────

def launch():
    """Start the Gradio server."""
    demo.launch(
        server_name="0.0.0.0",
        server_port=7860,
        share=False,
        show_error=True,
        theme=gr.themes.Soft(),
        css="""
            /* Make the app fill the viewport with no outer scroll */
            .gradio-container { max-width: 1200px !important; }

            /* Chatbot fills available space, input always visible */
            .chatbot-container { height: 65vh !important; min-height: 400px; }

            /* Tabs content scrolls independently if needed */
            .tabitem { overflow-y: auto; }
        """,
    )
