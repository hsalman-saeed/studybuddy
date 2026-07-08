"""
Cloud connectivity proof — demonstrates live Qwen Cloud API integration.

This file is a submission deliverable: it verifies that StudyBuddy's AI
processing runs through Qwen Cloud's managed infrastructure (DashScope),
not a local or third-party endpoint.
"""

from openai import OpenAI
from config import QWEN_API_KEY, QWEN_BASE_URL

PRIMARY_MODEL = "qwen3.7-plus"
PROJECT_NAME = "StudyBuddy"
TRACK_NAME = "Track 1 — MemoryAgent"


def verify_qwen_cloud_connection() -> bool:
    """Send a single request to Qwen Cloud and print a readable proof of connectivity."""

    border = "=" * 60
    print(border)
    print(f"  {PROJECT_NAME} — Qwen Cloud Connectivity Verification")
    print(f"  {TRACK_NAME}")
    print(f"  This script verifies a live connection to the Qwen Cloud API.")
    print(border)
    print()
    print(f"  Base URL : {QWEN_BASE_URL}")
    print(f"  Model    : {PRIMARY_MODEL}")
    print()

    try:
        client = OpenAI(api_key=QWEN_API_KEY, base_url=QWEN_BASE_URL)

        response = client.chat.completions.create(
            model=PRIMARY_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": "Reply with exactly this text and nothing else: StudyBuddy is connected to Qwen Cloud.",
                },
                {"role": "user", "content": "Confirm connection."},
            ],
            temperature=0,
            max_tokens=50,
        )

        reply = response.choices[0].message.content.strip()
        model_used = response.model
        usage = response.usage

        print(f"  Model response : {reply}")
        print(f"  Model name     : {model_used}")

        if usage:
            print(f"  Token usage    : prompt={usage.prompt_tokens}, "
                  f"completion={usage.completion_tokens}, "
                  f"total={usage.total_tokens}")

        print()
        print(border)
        print("  CONNECTION VERIFIED")
        print("  This application's AI processing runs through")
        print("  Qwen Cloud's managed infrastructure (DashScope).")
        print(border)
        return True

    except Exception as e:
        print()
        print(border)
        print(f"  CONNECTION FAILED")
        print(f"  Error: {e}")
        print(border)
        return False


if __name__ == "__main__":
    verify_qwen_cloud_connection()
