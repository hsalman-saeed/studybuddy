# StudyBuddy

**An AI study assistant with persistent, two-tier memory and spaced-repetition scheduling — built for Track 1 (MemoryAgent) of the Qwen Cloud Hackathon.**

---

## The Problem

Students study concepts once and forget them. Without structured review, retention drops sharply within days — a well-documented phenomenon described by Ebbinghaus's forgetting curve. Generic AI chatbots answer questions statelessly: they don't know what you studied yesterday, which concepts you struggle with, or when you're due for review.

## The Solution

StudyBuddy is an AI study assistant that **remembers everything you've studied across sessions**, tracks your mastery of each concept, and uses a spaced-repetition algorithm to tell you exactly when and what to review. It combines structured storage (SQLite) with semantic vector search (ChromaDB) so it can retrieve past study notes by topic name or by meaning. An agentic orchestration core routes through six tools automatically — saving sessions, generating quizzes, identifying weak areas, creating study plans, and updating review schedules — without requiring explicit commands from the student.

---

## Architecture

![StudyBuddy Architecture Diagram](architecture_diagram.png)

The system flows as follows: user messages enter through a Gradio web interface (Chat tab or Dashboard tab) and are routed to an agent orchestration core (`agent.py`) that operates in a ReAct-style tool-calling loop (max 5 iterations per turn). The agent decides which of 6 tools to invoke — each tool connects to the dual memory layer (SQLite for structured data, ChromaDB for semantic search), the SM-2 spaced-repetition engine, and/or the model router for LLM generation. The model router classifies query complexity using a lightweight classifier model, selects the appropriate Qwen model tier, and falls back across providers if the primary call fails. The resilience layer wraps all LLM calls with exponential-backoff retry logic.

---

## Key Features

### Two-Tier Memory System

- **Tier 1 — SQLite** (`memory_sqlite.py`): Four tables (`sessions`, `concepts`, `quiz_results`, `conversations`) store structured, queryable data. Concepts track mastery level (0–10), times studied, times correct/wrong, and spaced-repetition scheduling fields (ease factor, interval, next review date).
- **Tier 2 — ChromaDB** (`memory_vector.py`): Study notes are embedded using Qwen's `text-embedding-v4` model via a custom `QwenEmbeddingFunction` and stored in a persistent ChromaDB collection (`study_notes`). Semantic search finds related notes even when wording differs from the original, using cosine similarity.

### SM-2 Spaced Repetition

The spaced-repetition engine (`spaced_repetition.py`) implements the SM-2 algorithm. The core idea: when you correctly recall a concept, the interval before your next review grows exponentially (1 day → 6 days → ~15 days → ...). When you forget, the interval resets to 1 day. This models the Ebbinghaus forgetting curve — the observation that memory retention decays exponentially over time unless refreshed at increasing intervals. The engine stores `ease_factor` (minimum 1.3), `interval_days`, and `review_count` per concept, and the pure-function `calculate_sm2()` takes a quality score (0–5) to compute new scheduling parameters.

### Confidence-Based Model Routing

The model router (`model_router.py`) uses a three-tier system:
1. **Classifier** (`qwen3.6-plus`): A cheap, fast call that classifies each user message as `"simple"` or `"complex"` based on whether it requires synthesis across historical data.
2. **Default tier** (`qwen3.7-plus`): Handles simple queries (factual recall, session saving, greetings).
3. **Complex tier** (`qwen3.7-max`): Handles quiz generation, study plan creation, weak-area analysis.

Every routing decision is logged with timestamp, tier, model used, and fallback status for observability.

### Cross-Provider Resilience

The resilience layer (`resilience.py`) wraps all LLM generation in a three-level defense:
1. **Error classification**: Categorizes exceptions as retryable (rate limits, timeouts, 5xx errors, connection failures) or non-retryable (auth errors, invalid requests, content policy violations).
2. **Exponential backoff**: Retryable failures trigger delays of 2s, 4s, etc., up to `max_attempts` (default 3).
3. **Cross-provider fallback chain**: If the primary Qwen model fails entirely, the router sequentially attempts `glm-5.1` → `deepseek-v4-pro` → `deepseek-v4-flash`.

The outermost `safe_generate()` function guarantees it never raises an exception and always returns a dict with a `"text"` key.

### Dashboard Visualizations

The Dashboard tab (`visualizations.py`) renders four interactive Plotly charts:
1. **Mastery Snapshot**: Horizontal bar chart of all concepts, color-coded by mastery tier (red ≤3, orange ≤6, green >6).
2. **Accuracy Trend**: Line chart of cumulative quiz accuracy over attempts, with a 70% target line.
3. **Urgency Heatmap**: Bar chart scoring review urgency per concept using `(10 - mastery) + (times_wrong × 2)`, colored on a green-yellow-red scale.
4. **Study Streak**: 14-day calendar bar chart showing study activity, with current streak count in the title.

### Agentic Tool Orchestration

Six tools are defined in OpenAI function-calling schema format (`tools.py`) and dispatched by a single `execute_tool()` function:

| Tool | What it does |
|------|-------------|
| `save_study_session` | Saves to SQLite, embeds notes in ChromaDB, initializes SRS schedule for each concept |
| `get_study_history` | Queries SQLite by topic (LIKE match) and/or ChromaDB by semantic similarity |
| `generate_quiz` | Retrieves study context from both memory tiers, then prompts the complex-tier LLM to generate quiz JSON |
| `get_weak_areas` | Combines low-mastery concepts with SRS-overdue concepts into a ranked priority list |
| `create_study_plan` | Builds a day-by-day study plan via the complex-tier LLM, prioritizing weak/overdue concepts |
| `record_quiz_answer` | Saves the quiz result, updates mastery (±1, clamped 0–10), and recalculates the SRS schedule |

The agent (`agent.py`) uses Qwen's native function-calling API (`tool_choice="auto"`) with a detailed system prompt that instructs proactive tool usage.

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Language | Python 3.10+ |
| LLM API | Qwen Cloud (DashScope) via OpenAI-compatible SDK |
| Models | qwen3.6-plus, qwen3.7-plus, qwen3.7-max |
| Embeddings | text-embedding-v4 |
| Fallback Models | glm-5.1, deepseek-v4-pro, deepseek-v4-flash |
| Structured Storage | SQLite (via stdlib `sqlite3`) |
| Vector Storage | ChromaDB (persistent client) |
| Web Interface | Gradio |
| Visualizations | Plotly |
| Environment | python-dotenv |

---

## Quick Start

### Prerequisites

- Python 3.10 or higher
- A Qwen Cloud API key (from [DashScope](https://dashscope.aliyun.com))

### Installation

```bash
# Clone the repository
git clone <repo-url>
cd studybuddy

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env and add your credentials:
#   QWEN_API_KEY=your-api-key-here
#   QWEN_BASE_URL=https://dashscope-intl.aliyuncs.com/compatible-mode/v1
```

### Run

```bash
python main.py
```

The app will start on `http://0.0.0.0:7860`. Open it in your browser.

### Verify Cloud Connectivity

```bash
python cloud_proof.py
```

This sends a single request to Qwen Cloud and prints a detailed proof of connectivity, including model name and token usage.

---

## Project Structure

```
studybuddy/
├── main.py                  # Entry point — validates env, launches Gradio
├── agent.py                 # Agent orchestration core (ReAct tool-calling loop)
├── tools.py                 # 6 tools with OpenAI function-calling schema
├── memory_sqlite.py         # Tier 1: SQLite structured storage (4 tables)
├── memory_vector.py         # Tier 2: ChromaDB semantic vector store
├── spaced_repetition.py     # SM-2 spaced-repetition scheduling engine
├── model_router.py          # 3-tier model routing with complexity classifier
├── resilience.py            # Retry logic, error classification, fallback chain
├── ui.py                    # Gradio interface (Chat tab + Dashboard tab)
├── visualizations.py        # 4 Plotly dashboard charts + streak calculator
├── cloud_proof.py           # Qwen Cloud connectivity verification script
├── config.py                # Central config loader (env vars)
├── requirements.txt         # Python dependencies
├── .env.example             # Template for environment variables
├── LICENSE                  # MIT License
├── architecture_diagram.png # System architecture diagram
├── test_memory_sqlite.py    # Tests for SQLite memory layer
├── test_memory_vector.py    # Tests for vector memory layer
├── test_spaced_repetition.py # Tests for SM-2 algorithm
├── test_model_router.py     # Tests for model routing
├── test_resilience.py       # Tests for resilience layer
├── test_tools.py            # Tests for tool execution
├── test_agent.py            # Tests for agent orchestration
└── test_visualizations.py   # Tests for visualization functions
```

---

## Alibaba Cloud / Qwen Cloud Integration

StudyBuddy runs entirely on Qwen Cloud's managed API infrastructure (DashScope). All LLM inference (chat completions across three model tiers), complexity classification, and text embeddings are served through the `dashscope-intl.aliyuncs.com` endpoint via the OpenAI-compatible API.

The `cloud_proof.py` script verifies this live connection by sending a single request and printing the base URL, model name, response content, and token usage — providing auditable proof that no local or third-party inference is used for primary AI processing.

---

## Judging Criteria Mapping

| Criterion | Weight | Feature | Implementation Detail |
|-----------|--------|---------|----------------------|
| **Innovation & AI Creativity** | 30% | Two-tier memory architecture | SQLite for structured queries + ChromaDB for semantic similarity search — the agent retrieves context by both exact topic match and meaning-based search |
| | | SM-2 spaced repetition | Models the Ebbinghaus forgetting curve with per-concept ease factors, exponentially growing intervals, and automatic review scheduling |
| | | Proactive tool use | System prompt instructs the agent to use tools without waiting for explicit commands (e.g., auto-saving sessions when a student describes what they studied) |
| **Technical Depth & Engineering** | 30% | 3-tier model routing | Lightweight classifier dispatches to cost-appropriate model tiers; logged for observability |
| | | Cross-provider fallback | Primary Qwen models fail over to GLM-5.1 → DeepSeek-v4-Pro → DeepSeek-v4-Flash |
| | | Resilience layer | Error classification (retryable vs. non-retryable), exponential backoff, bulletproof `safe_generate()` wrapper |
| | | Native function calling | Agent uses Qwen's tool-calling API in a ReAct-style loop with max 5 iterations and loop-exhaustion handling |
| **Problem Value & Impact** | 25% | Persistent memory across sessions | SQLite + ChromaDB data persists on disk — restarting the app preserves all study history |
| | | Personalized quizzes | Quiz generation pulls from the student's actual study history and semantic notes, not generic trivia |
| | | Weak-area identification | Combines low-mastery scores with SRS overdue dates for a ranked priority list |
| | | Study plan creation | Day-by-day plans prioritize overdue and weak concepts with time allocations |
| **Presentation & Documentation** | 15% | Architecture diagram | Professional, color-coded diagram showing all system layers and data flows |
| | | Dashboard | 4 interactive Plotly visualizations (mastery, accuracy trend, urgency, streak) |
| | | Cloud proof script | Auditable verification of Qwen Cloud connectivity |

---

## License

MIT License. See [LICENSE](LICENSE).

---

## Future Work

- **Multi-user authentication**: The current design is single-user by architecture — one SQLite database and one ChromaDB collection serve all data. Adding user isolation would require per-user namespacing in both storage layers.
- **Independent quiz-answer verification**: The agent determines answer correctness via its own LLM judgment (as instructed in the system prompt), accepting reasonable paraphrases rather than requiring exact string matches. There is no independent, deterministic verification layer beyond the model's own judgment.
- **Concept-name granularity in quiz scoring**: `record_quiz_answer` and `save_quiz_result` currently use the session's `topic` as the concept name for mastery/SRS updates rather than inferring the specific sub-concept a question actually tests. Broader topics may absorb mastery signal that should apply to a narrower concept.
- **ChromaDB embedding function serialization**: The custom `QwenEmbeddingFunction` implements `name()`, `get_config()`, and `build_from_config()` per ChromaDB's current embedding function protocol. If ChromaDB's internal serialization requirements change in a future version, this may need updating.
- **Tool-loop failure visibility**: If tool execution raises an exception inside the agent's ReAct loop, it's caught and returned as an error JSON string to keep the loop alive, but repeated failures within the 5-iteration cap could still produce a confusing final response in edge cases.