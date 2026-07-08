"""Standalone smoke test for VectorMemoryManager — adds notes and verifies semantic ranking."""

import os
import shutil

# Use a throwaway ChromaDB directory so we don't pollute the real one
TEST_CHROMA_PATH = "test_chroma_db"
if os.path.exists(TEST_CHROMA_PATH):
    shutil.rmtree(TEST_CHROMA_PATH)

os.environ["CHROMA_PATH"] = TEST_CHROMA_PATH

from memory_vector import VectorMemoryManager

vmm = VectorMemoryManager()

# 1. Add 3 notes: two about loops (conceptually overlapping), one about recursion (unrelated)
print("\n--- Adding notes ---")

r1 = vmm.add_note(
    session_id="test-001",
    topic="Python Basics",
    concepts=["for loops", "iteration"],
    text="A for loop in Python iterates over a sequence like a list or range, executing the body for each element.",
)
print(f"Note 1 (for loops): {r1}")

r2 = vmm.add_note(
    session_id="test-001",
    topic="Python Basics",
    concepts=["while loops", "iteration"],
    text="A while loop repeatedly executes a block of code as long as a condition remains true, useful when the number of iterations is unknown.",
)
print(f"Note 2 (while loops): {r2}")

r3 = vmm.add_note(
    session_id="test-002",
    topic="Advanced Python",
    concepts=["recursion", "functions"],
    text="Recursion is when a function calls itself to solve a smaller subproblem, with a base case to stop the infinite descent.",
)
print(f"Note 3 (recursion): {r3}")

# 2. Semantic search — "iterating over a list repeatedly" should rank loop notes above recursion
print("\n--- semantic_search('iterating over a list repeatedly') ---")
search = vmm.semantic_search("iterating over a list repeatedly", n_results=3)
print(f"Success: {search['success']}")
if not search["success"]:
    print(f"Error: {search.get('error', 'unknown')}")
for i, result in enumerate(search["results"], 1):
    print(f"  #{i} | score={result['similarity_score']:.4f} | topic={result['topic']} | concepts={result['concepts']}")
    print(f"       text: {result['text'][:80]}...")

# 3. Verify ranking: loop notes should rank above recursion
print("\n--- Ranking verification ---")
topics = [r["concepts"] for r in search["results"]]
loop_indices = [i for i, c in enumerate(topics) if "loop" in c.lower()]
recursion_indices = [i for i, c in enumerate(topics) if "recursion" in c.lower()]

if loop_indices and recursion_indices and max(loop_indices) < min(recursion_indices):
    print("PASS: Both loop-related notes rank above the recursion note.")
else:
    print(f"INFO: loop positions={loop_indices}, recursion positions={recursion_indices}")
    if loop_indices and recursion_indices and loop_indices[0] < recursion_indices[0]:
        print("PARTIAL: At least one loop note ranks above recursion.")
    else:
        print("WARN: Recursion note ranked above one or more loop notes — check embedding quality.")

# 4. Collection count
print(f"\n--- get_collection_count ---")
print(f"Total notes stored: {vmm.get_collection_count()}")

# Cleanup
del vmm
try:
    shutil.rmtree(TEST_CHROMA_PATH, ignore_errors=True)
    print("\nTest ChromaDB cleaned up.")
except Exception as e:
    print(f"\nCleanup note: {e} (files may persist until process exits)")
