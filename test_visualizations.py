"""Tests for the visualization layer — streak logic and chart generation."""

import json
from datetime import datetime, timedelta

from visualizations import (
    calculate_streak,
    create_mastery_snapshot_chart,
    create_accuracy_trend_chart,
    create_urgency_heatmap,
    create_streak_chart,
    get_dashboard_summary,
)


def test_calculate_streak():
    """Test streak calculation with a known 3-day current streak."""
    today = datetime.now().date()
    dates = [
        (today - timedelta(days=0)).strftime("%Y-%m-%d"),       # today
        (today - timedelta(days=1)).strftime("%Y-%m-%d"),       # yesterday
        (today - timedelta(days=2)).strftime("%Y-%m-%d"),       # 2 days ago
        (today - timedelta(days=10)).strftime("%Y-%m-%d"),      # old scattered date
        (today - timedelta(days=15)).strftime("%Y-%m-%d"),      # another old date
    ]

    result = calculate_streak(dates)
    print(f"  calculate_streak result: {json.dumps(result)}")
    assert result["current_streak"] == 3, f"Expected 3, got {result['current_streak']}"
    assert result["longest_streak"] == 3, f"Expected 3, got {result['longest_streak']}"
    assert result["total_days_studied"] == 5, f"Expected 5, got {result['total_days_studied']}"
    print("  [PASS] current_streak=3, longest_streak=3, total_days_studied=5")

    # Edge case: empty list
    empty = calculate_streak([])
    assert empty == {"current_streak": 0, "longest_streak": 0, "total_days_studied": 0}
    print("  [PASS] empty list returns all zeros")

    # Edge case: duplicates
    dupes = dates + [dates[0], dates[1]]
    dup_result = calculate_streak(dupes)
    assert dup_result["total_days_studied"] == 5
    print("  [PASS] duplicates handled correctly")


def test_chart_generation():
    """Generate each chart and save as HTML for visual inspection."""
    charts = {
        "mastery_snapshot": create_mastery_snapshot_chart,
        "accuracy_trend": create_accuracy_trend_chart,
        "urgency_heatmap": create_urgency_heatmap,
        "streak_chart": create_streak_chart,
    }

    saved_files = []
    for name, func in charts.items():
        fig = func()
        filename = f"test_chart_{name}.html"
        fig.write_html(filename)
        saved_files.append(filename)
        print(f"  Saved: {filename} (data points: {len(fig.data)})")

    return saved_files


def test_dashboard_summary():
    """Print the combined dashboard summary dict."""
    summary = get_dashboard_summary()
    print(f"  Dashboard summary: {json.dumps(summary, indent=2, default=str)}")


if __name__ == "__main__":
    print("=" * 60)
    print("TEST 1: calculate_streak()")
    print("=" * 60)
    test_calculate_streak()
    print()

    print("=" * 60)
    print("TEST 2: Chart generation (4 HTML files)")
    print("=" * 60)
    files = test_chart_generation()
    print(f"\n  Generated files: {files}")
    print()

    print("=" * 60)
    print("TEST 3: Dashboard summary")
    print("=" * 60)
    test_dashboard_summary()
    print()

    print("=" * 60)
    print("All visualization tests complete.")
    print("=" * 60)
