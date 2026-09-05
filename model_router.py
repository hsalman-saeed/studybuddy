"""Qwen model-routing layer that dispatches LLM calls across task complexity tiers."""

import json
from datetime import datetime, timezone

from openai import OpenAI

from config import (
    QWEN_API_KEY,
    QWEN_BASE_URL,
    QWEN_CLASSIFIER_MODEL,
    QWEN_DEFAULT_MODEL,
    QWEN_COMPLEX_MODEL,
)

# ── Module-level constants ──────────────────────────────────────────────

CLASSIFIER_MODEL = QWEN_CLASSIFIER_MODEL
DEFAULT_MODEL = QWEN_DEFAULT_MODEL
COMPLEX_MODEL = QWEN_COMPLEX_MODEL

# ── Module-level state ──────────────────────────────────────────────────

_client = OpenAI(api_key=QWEN_API_KEY, base_url=QWEN_BASE_URL)
ROUTING_LOG: list[dict] = []


# ── Classification ──────────────────────────────────────────────────────

def classify_complexity(user_message: str) -> dict:
    """Send a minimal, cheap request to classify a message as simple or complex."""
    try:
        system_prompt = (
            'Classify the user message as "simple" or "complex" based on these criteria:\n'
            'SIMPLE: direct factual recall, saving a study session, short clarifying '
            'questions, greetings.\n'
            'COMPLEX: quiz generation, weak-area analysis requiring synthesis across '
            'multiple past sessions, study plan creation, anything requiring reasoning '
            'over historical data.\n'
            'Respond with ONLY a JSON object: {"tier": "simple"} or {"tier": "complex"} '
            "— nothing else, no explanation, no markdown fences."
        )
        response = _client.chat.completions.create(
            model=CLASSIFIER_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            max_tokens=20,
            temperature=0,
        )
        raw = response.choices[0].message.content.strip()

        # Strip markdown fences if present
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

        try:
            parsed = json.loads(raw)
            tier = parsed.get("tier", "")
            if tier not in ("simple", "complex"):
                tier = "simple"
        except (json.JSONDecodeError, AttributeError):
            tier = "simple"

        return {"tier": tier, "raw_response": raw}
    except Exception as e:
        return {"tier": "simple", "raw_response": "classification_failed"}


# ── Qwen-only generation ────────────────────────────────────────────────

def generate(messages: list, force_tier: str = None) -> dict:
    """Route a generation request through the classifier to a Qwen model tier."""
    # Step 1: Determine tier
    if force_tier in ("simple", "complex"):
        tier = force_tier
    else:
        # Extract last user message
        user_content = None
        for msg in reversed(messages):
            if msg.get("role") == "user":
                user_content = msg.get("content", "")
                break
        if user_content is None:
            user_content = ""
        classification = classify_complexity(user_content)
        tier = classification["tier"]

    # Step 2: Select primary model
    primary_model = COMPLEX_MODEL if tier == "complex" else DEFAULT_MODEL

    # Step 3: Attempt the selected Qwen model
    result_text = None
    model_used = None
    fallback_used = False
    primary_failed = False

    try:
        response = _client.chat.completions.create(
            model=primary_model,
            messages=messages,
        )
        result_text = response.choices[0].message.content
        model_used = primary_model
    except Exception:
        primary_failed = True

    # Step 5: Build result
    if result_text is not None:
        result = {
            "success": True,
            "text": result_text,
            "model_used": model_used,
            "tier": tier,
            "fallback_used": fallback_used,
        }
        if primary_failed:
            result["primary_model_failed"] = primary_model
    else:
        result = {
            "success": False,
            "error": "Qwen generation failed",
            "tier": tier,
            "attempted_models": [primary_model],
        }

    # Step 6: Log entry
    log_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "tier": tier,
        "model_used": model_used,
        "fallback_used": fallback_used,
        "success": result.get("success", False),
    }
    ROUTING_LOG.append(log_entry)

    # Console log for demo observability
    fallback_marker = " [FALLBACK]" if fallback_used else ""
    print(
        f"[Router] tier={tier} | model={model_used or 'NONE'}{fallback_marker} | "
        f"success={result.get('success', False)}"
    )

    return result


# ── Query helpers ───────────────────────────────────────────────────────

def get_routing_log(limit: int = 20) -> list:
    """Return the most recent `limit` entries from ROUTING_LOG (most recent first)."""
    return list(reversed(ROUTING_LOG[-limit:]))


def get_routing_stats() -> dict:
    """Compute aggregate stats from ROUTING_LOG."""
    total_calls = len(ROUTING_LOG)
    simple_tier_count = sum(1 for e in ROUTING_LOG if e.get("tier") == "simple")
    complex_tier_count = sum(1 for e in ROUTING_LOG if e.get("tier") == "complex")
    fallback_used_count = sum(1 for e in ROUTING_LOG if e.get("fallback_used"))

    per_model: dict[str, int] = {}
    for e in ROUTING_LOG:
        model = e.get("model_used")
        if model:
            per_model[model] = per_model.get(model, 0) + 1

    return {
        "total_calls": total_calls,
        "simple_tier_count": simple_tier_count,
        "complex_tier_count": complex_tier_count,
        "fallback_used_count": fallback_used_count,
        "per_model_usage": per_model,
    }
