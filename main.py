"""Entry point for the StudyBuddy application."""

import sys

from config import QWEN_API_KEY, QWEN_BASE_URL


def main():
    if not QWEN_API_KEY or not QWEN_BASE_URL:
        print(
            "Error: QWEN_API_KEY and QWEN_BASE_URL must be set in your .env file.\n"
            "Copy .env.example to .env and fill in your credentials."
        )
        sys.exit(1)

    print("StudyBuddy starting — environment verified.")
    print(f"  API base URL: {QWEN_BASE_URL}")
    print(f"  API key: {'*' * 4}...{QWEN_API_KEY[-4:]}" if len(QWEN_API_KEY) > 4 else "  API key: set")

    from memory_sqlite import MemoryManager
    seed_result = MemoryManager().seed_demo_data_if_empty()
    if seed_result.get("seeded"):
        print("Demo data seeded for a fresh StudyBuddy database.")
    print("  Default demo account: username='demo_student', password='demo123'")

    from ui import launch
    launch()


if __name__ == "__main__":
    main()
