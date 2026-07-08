"""One-time diagnostic script that verifies API connectivity for every model the project will use."""

import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

API_KEY = os.getenv("QWEN_API_KEY")
BASE_URL = os.getenv("QWEN_BASE_URL")

if not API_KEY or not BASE_URL:
    print("ERROR: QWEN_API_KEY or QWEN_BASE_URL not found in .env")
    exit(1)

client = OpenAI(api_key=API_KEY, base_url=BASE_URL)

TEXT_MODELS = [
    "qwen3.6-plus",
    "qwen3.7-plus",
    "qwen3.7-max",
    "glm-5.1",
    "deepseek-v4-pro",
    "deepseek-v4-flash",
]

EMBEDDING_MODEL = "text-embedding-v4"

results = []


def test_text_model(model_name):
    print(f"\n--- Testing text model: {model_name} ---")
    try:
        response = client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": "Reply with only the word: OK"}],
        )
        reply = response.choices[0].message.content
        usage = response.usage
        usage_str = ""
        if usage:
            usage_str = f"tokens: prompt={usage.prompt_tokens}, completion={usage.completion_tokens}, total={usage.total_tokens}"
        print(f"  Model : {model_name}")
        print(f"  Status: PASS")
        print(f"  Reply : {reply}")
        if usage_str:
            print(f"  Usage : {usage_str}")
        results.append((model_name, "PASS", reply.strip()))
    except Exception as e:
        print(f"  Model : {model_name}")
        print(f"  Status: FAIL")
        print(f"  Error : {e}")
        results.append((model_name, "FAIL", str(e)))


def test_embedding_model(model_name):
    print(f"\n--- Testing embedding model: {model_name} ---")
    try:
        response = client.embeddings.create(
            model=model_name,
            input="test embedding",
        )
        vector = response.data[0].embedding
        dim = len(vector)
        print(f"  Model    : {model_name}")
        print(f"  Status   : PASS")
        print(f"  Dimension: {dim}")
        results.append((model_name, "PASS", f"dimension={dim}"))
    except Exception as e:
        print(f"  Model : {model_name}")
        print(f"  Status: FAIL")
        print(f"  Error : {e}")
        results.append((model_name, "FAIL", str(e)))


for model in TEXT_MODELS:
    test_text_model(model)

test_embedding_model(EMBEDDING_MODEL)

# Final summary table
print("\n" + "=" * 80)
print(f"{'MODEL':<25} | {'STATUS':<6} | {'NOTES'}")
print("-" * 80)
for name, status, notes in results:
    print(f"{name:<25} | {status:<6} | {notes}")
print("=" * 80)
