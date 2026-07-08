"""Visualization layer that renders charts and progress dashboards for study metrics."""

import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta

from memory_sqlite import MemoryManager

# ── Module-level read-only accessor ─────────────────────────────────────

memory = MemoryManager()


# ── STEP 1: Pure streak calculation (no database, fully testable) ──────

def calculate_streak(session_dates: list) -> dict:
    """Calculate study streak stats from a list of YYYY-MM-DD date strings."""
    if not session_dates:
        return {"current_streak": 0, "longest_streak": 0, "total_days_studied": 0}

    unique_dates = sorted(set(datetime.strptime(d, "%Y-%m-%d").date() for d in session_dates))
    total_days_studied = len(unique_dates)

    if total_days_studied == 0:
        return {"current_streak": 0, "longest_streak": 0, "total_days_studied": 0}

    # Calculate longest streak
    longest_streak = 1
    current_run = 1
    for i in range(1, total_days_studied):
        if unique_dates[i] - unique_dates[i - 1] == timedelta(days=1):
            current_run += 1
            longest_streak = max(longest_streak, current_run)
        else:
            current_run = 1

    # Calculate current streak (must end today or yesterday)
    today = datetime.now().date()
    yesterday = today - timedelta(days=1)
    most_recent = unique_dates[-1]

    if most_recent not in (today, yesterday):
        current_streak = 0
    else:
        current_streak = 1
        for i in range(total_days_studied - 2, -1, -1):
            if unique_dates[i + 1] - unique_dates[i] == timedelta(days=1):
                current_streak += 1
            else:
                break

    return {
        "current_streak": current_streak,
        "longest_streak": longest_streak,
        "total_days_studied": total_days_studied,
    }


# ── STEP 2: Chart-generation functions ──────────────────────────────────

def _empty_figure(message: str) -> go.Figure:
    """Return a blank figure with a centered text annotation."""
    fig = go.Figure()
    fig.add_annotation(
        text=message,
        xref="paper", yref="paper",
        x=0.5, y=0.5,
        showarrow=False,
        font=dict(size=14),
    )
    fig.update_layout(
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
        plot_bgcolor="white",
    )
    return fig


def create_mastery_snapshot_chart() -> go.Figure:
    """Horizontal bar chart of concept mastery levels, color-coded by tier."""
    concepts = memory.get_all_concepts_with_details()
    if not concepts:
        return _empty_figure("No concepts studied yet — start a study session!")

    names = [c["concept_name"] for c in concepts]
    levels = [c["mastery_level"] for c in concepts]
    colors = []
    for lvl in levels:
        if lvl <= 3:
            colors.append("red")
        elif lvl <= 6:
            colors.append("orange")
        else:
            colors.append("green")

    # Sort so lowest mastery appears at top (first in reversed list for bar chart)
    paired = list(zip(names, levels, colors))
    paired.sort(key=lambda x: x[1], reverse=True)
    names, levels, colors = zip(*paired)

    fig = go.Figure(go.Bar(
        x=levels,
        y=list(names),
        orientation="h",
        marker=dict(color=list(colors)),
    ))
    fig.update_layout(
        title="Concept Mastery Levels",
        xaxis=dict(title="Mastery (0-10)", range=[0, 10]),
        yaxis=dict(title="Concept", autorange="reversed"),
        height=max(300, len(names) * 30 + 100),
    )
    return fig


def create_accuracy_trend_chart() -> go.Figure:
    """Line chart of cumulative quiz accuracy over time."""
    history = memory.get_quiz_history_chronological(limit=200)
    if len(history) < 2:
        return _empty_figure(
            "Not enough quiz data yet — answer some quiz questions "
            "to see your progress trend!"
        )

    cumulative_correct = 0
    cumulative_total = 0
    attempts = []
    accuracies = []

    for entry in history:
        cumulative_total += 1
        if entry["is_correct"]:
            cumulative_correct += 1
        attempts.append(cumulative_total)
        accuracies.append(round((cumulative_correct / cumulative_total) * 100, 1))

    fig = go.Figure(go.Scatter(
        x=attempts,
        y=accuracies,
        mode="lines+markers",
        name="Cumulative Accuracy",
    ))
    fig.add_hline(
        y=70, line_dash="dash", line_color="gray",
        annotation_text="Target accuracy",
    )
    fig.update_layout(
        title="Quiz Accuracy Trend Over Time",
        xaxis=dict(title="Quiz Attempt"),
        yaxis=dict(title="Accuracy (%)", range=[0, 100]),
    )
    return fig


def create_urgency_heatmap() -> go.Figure:
    """Bar chart showing review urgency by concept (red=urgent, green=mastered)."""
    concepts = memory.get_all_concepts_with_details()
    if not concepts:
        return _empty_figure("No concepts studied yet — start a study session!")

    names = []
    urgency_scores = []
    for c in concepts:
        score = (10 - c["mastery_level"]) + (c["times_wrong"] * 2)
        names.append(c["concept_name"])
        urgency_scores.append(score)

    # Sort by urgency descending (most urgent at top)
    paired = list(zip(names, urgency_scores))
    paired.sort(key=lambda x: x[1], reverse=True)
    names, urgency_scores = zip(*paired)

    fig = go.Figure(go.Bar(
        x=list(urgency_scores),
        y=list(names),
        orientation="h",
        marker=dict(
            color=list(urgency_scores),
            colorscale=[[0, "green"], [0.5, "yellow"], [1, "red"]],
            showscale=True,
            colorbar=dict(title="Urgency"),
        ),
    ))
    fig.update_layout(
        title="Review Urgency by Concept",
        xaxis=dict(title="Urgency Score"),
        yaxis=dict(title="Concept", autorange="reversed"),
        height=max(300, len(names) * 30 + 100),
    )
    return fig


def create_streak_chart() -> go.Figure:
    """Bar chart showing study activity for the last 14 calendar days."""
    session_dates = memory.get_all_session_dates()
    streak_info = calculate_streak(session_dates)
    current_streak = streak_info["current_streak"]

    studied_set = set(session_dates)
    today = datetime.now().date()
    days = [(today - timedelta(days=i)) for i in range(13, -1, -1)]

    labels = [d.strftime("%Y-%m-%d") for d in days]
    values = [1 if d.strftime("%Y-%m-%d") in studied_set else 0 for d in days]
    colors = ["green" if v == 1 else "lightgray" for v in values]

    short_labels = [d.strftime("%a\n%m/%d") for d in days]

    fig = go.Figure(go.Bar(
        x=short_labels,
        y=values,
        marker=dict(color=colors),
    ))
    fig.update_layout(
        title=f"Study Streak: {current_streak} day(s) in a row",
        xaxis=dict(title="Date"),
        yaxis=dict(title="Studied", range=[0, 1.5], tickvals=[0, 1],
                   ticktext=["No", "Yes"]),
    )
    return fig


def get_dashboard_summary() -> dict:
    """Combined stats + streak data as a single flat dict."""
    stats = memory.get_overall_stats()
    streak = calculate_streak(memory.get_all_session_dates())

    combined = {}
    if isinstance(stats, dict):
        combined.update(stats)
    combined.update(streak)
    return combined
