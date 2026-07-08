"""Agent orchestration core that coordinates memory, model routing, and tool execution."""

import json
import uuid

from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception

from config import QWEN_API_KEY, QWEN_BASE_URL
from tools import TOOLS, execute_tool
from resilience import safe_generate, classify_retryable_error
from memory_sqlite import MemoryManager

# ── Module-level constants ──────────────────────────────────────────────

AGENT_MODEL = "qwen3.7-plus"
_client = OpenAI(api_key=QWEN_API_KEY, base_url=QWEN_BASE_URL)


def _retryable_api_call(**kwargs):
    """Wrap a single chat.completions.create call with tenacity retry."""
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=4),
        retry=retry_if_exception(classify_retryable_error),
        before_sleep=lambda retry_state: print(
            f"[Agent] Retrying after transient error (attempt {retry_state.attempt_number})..."
        ),
    )
    def _call():
        return _client.chat.completions.create(**kwargs)

    return _call()


SYSTEM_PROMPT = """You are StudyBuddy, an AI study assistant with persistent memory across sessions. You remember everything a student has studied, track their mastery of each concept, and know exactly when they are due for review based on spaced-repetition scheduling.

Your personality: patient, encouraging, specific. Never make a student feel bad for forgetting something — forgetting is expected and is exactly why you exist.

You have access to 6 tools. Use them proactively, not just when explicitly asked:

- save_study_session: call this whenever the student describes something they just learned or studied, even if they didn't explicitly say 'save this.' Extract the topic, list the specific concepts covered, and write session_text summarizing what they told you in your own words for accurate semantic recall later.

- get_study_history: call this when the student asks what they've studied before, when you need context before helping with a topic, or when they ask you to review something. Use semantic_query when their question is about meaning/topic rather than an exact title.

- generate_quiz: call this when the student asks to be quizzed or tested, or when you want to proactively suggest practice on a topic they're due to review.

- get_weak_areas: call this when the student asks what to focus on, what they're struggling with, or before creating a study plan.

- create_study_plan: call this when the student states a goal and timeframe (an exam date, a deadline, a number of days).

- record_quiz_answer: call this immediately after the student answers a quiz question you generated, to update their mastery and review schedule. Determine is_correct by comparing their answer to the correct_answer using your own judgment (accept reasonable paraphrases, not just exact string matches).

Always check get_study_history or get_weak_areas before deep-diving into a topic if you don't already have context from this conversation. Reference specific past sessions and mastery levels naturally when relevant — this is what makes you different from a stateless chatbot."""


# ── StudyBuddy Agent ────────────────────────────────────────────────────

class StudyBuddyAgent:
    """Conversational orchestration agent with tool-calling capabilities."""

    def __init__(self):
        self.session_id = str(uuid.uuid4())
        self.conversation_history = []
        self._conv_memory = MemoryManager()
        print(f"StudyBuddyAgent initialized. Session: {self.session_id[:8]}...")

        # Restore previous conversation turns for continuity
        history = self._conv_memory.get_conversation_history(session_id=None, limit=10)
        if history:
            # get_conversation_history returns DESC (newest first); reverse for chronological order
            history.reverse()
            for turn in history:
                self.conversation_history.append({
                    "role": turn["role"],
                    "content": turn["content"],
                })
            print(f"[Agent] Restored {len(history)} previous conversation turns.")

    def chat(self, user_message: str) -> str:
        """Main entry point — process one user message with optional tool calls."""
        # Step 1: Append user message
        self.conversation_history.append({"role": "user", "content": user_message})
        self._conv_memory.save_conversation_turn(self.session_id, "user", user_message)

        # Step 2: Build full messages list
        messages = [{"role": "system", "content": SYSTEM_PROMPT}] + self.conversation_history

        # Step 3: Call the model with tool-calling enabled (retry-protected)
        try:
            response = _retryable_api_call(
                model=AGENT_MODEL,
                messages=messages,
                tools=TOOLS,
                tool_choice="auto",
                max_tokens=1500,
            )
        except Exception as e:
            return "I'm having trouble right now — please try again in a moment."

        # Step 4: Tool-calling loop (max 5 iterations)
        message = response.choices[0].message
        iteration_count = 0

        while message.tool_calls and iteration_count < 5:
            iteration_count += 1

            # Append assistant's tool-call message to history
            tool_calls_list = []
            for tool_call in message.tool_calls:
                tool_calls_list.append({
                    "id": tool_call.id,
                    "type": tool_call.type,
                    "function": {
                        "name": tool_call.function.name,
                        "arguments": tool_call.function.arguments,
                    },
                })

            self.conversation_history.append({
                "role": "assistant",
                "content": message.content or "",
                "tool_calls": tool_calls_list,
            })

            # Execute each tool call and append results
            for tool_call in message.tool_calls:
                tool_name = tool_call.function.name
                tool_args_str = tool_call.function.arguments
                print(f"[Agent] Calling tool: {tool_name}")

                # Parse arguments
                try:
                    tool_args = json.loads(tool_args_str)
                except json.JSONDecodeError:
                    tool_args = {}

                # Execute tool
                result = execute_tool(tool_name, tool_args)

                # Append tool result to history
                self.conversation_history.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result,
                })

            # Re-call with updated messages (retry-protected)
            messages = [{"role": "system", "content": SYSTEM_PROMPT}] + self.conversation_history
            try:
                response = _retryable_api_call(
                    model=AGENT_MODEL,
                    messages=messages,
                    tools=TOOLS,
                    tool_choice="auto",
                    max_tokens=1500,
                )
            except Exception as e:
                return "I'm having trouble right now — please try again in a moment."

            message = response.choices[0].message

        # Handle loop exhaustion
        if iteration_count >= 5 and message.tool_calls:
            self.conversation_history.append({
                "role": "user",
                "content": "Please provide your final response now without calling any more tools.",
            })
            messages = [{"role": "system", "content": SYSTEM_PROMPT}] + self.conversation_history
            try:
                response = _retryable_api_call(
                    model=AGENT_MODEL,
                    messages=messages,
                    tools=TOOLS,
                    tool_choice="none",
                    max_tokens=1500,
                )
                message = response.choices[0].message
            except Exception as e:
                return "I'm having trouble right now — please try again in a moment."

        # Step 5: Extract final text
        final_text = message.content or "I processed that but don't have a text response — could you rephrase?"

        # Step 6: Append assistant's final response
        self.conversation_history.append({"role": "assistant", "content": final_text})
        self._conv_memory.save_conversation_turn(self.session_id, "assistant", final_text)

        # Step 7: Return
        return final_text

    def get_session_summary(self) -> dict:
        """Return summary stats for this session."""
        turn_count = sum(1 for msg in self.conversation_history if msg.get("role") == "user")
        return {
            "session_id": self.session_id,
            "turn_count": turn_count,
            "started_at": None,
        }

    def reset_session(self) -> str:
        """Clear conversation history and start a new session."""
        self.conversation_history = []
        self.session_id = str(uuid.uuid4())
        return "New session started. Your long-term memory is unaffected — only this conversation's context has been cleared."
