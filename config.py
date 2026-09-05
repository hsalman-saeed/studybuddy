"""Central configuration loader that reads environment variables and application settings."""

import os
from dotenv import load_dotenv

load_dotenv()

DB_PATH = os.getenv("DB_PATH", "studybuddy.db")
CHROMA_PATH = os.getenv("CHROMA_PATH", "chroma_db")
QWEN_API_KEY = os.getenv("QWEN_API_KEY", "")
QWEN_BASE_URL = os.getenv("QWEN_BASE_URL", "")

QWEN_CLASSIFIER_MODEL = "qwen3.6-plus"
QWEN_DEFAULT_MODEL = "qwen3.7-plus"
QWEN_COMPLEX_MODEL = "qwen3.7-max"
QWEN_AGENT_MODEL = "qwen3.7-plus"
QWEN_EMBEDDING_MODEL = "text-embedding-v4"
