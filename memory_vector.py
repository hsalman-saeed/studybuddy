"""Vector store memory layer for semantic similarity search over learned content."""

from datetime import date
from uuid import uuid4

import chromadb
from openai import OpenAI

from config import CHROMA_PATH, QWEN_API_KEY, QWEN_BASE_URL, QWEN_EMBEDDING_MODEL
from memory_sqlite import DEFAULT_STUDENT_ID

EMBEDDING_MODEL = QWEN_EMBEDDING_MODEL


class QwenEmbeddingFunction:
    """Custom ChromaDB embedding function using Qwen's text-embedding-v4 via OpenAI-compatible API."""

    def __init__(self):
        self._client = OpenAI(api_key=QWEN_API_KEY, base_url=QWEN_BASE_URL)

    def __call__(self, input: list[str]) -> list[list[float]]:
        response = self._client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=input,
        )
        return [item.embedding for item in response.data]

    def embed_query(self, input: list[str]) -> list[list[float]]:
        return self(input)

    @staticmethod
    def name() -> str:
        return "qwen_embedding_function"

    def get_config(self) -> dict:
        return {"model": EMBEDDING_MODEL, "base_url": QWEN_BASE_URL}

    @staticmethod
    def build_from_config(config: dict) -> "QwenEmbeddingFunction":
        return QwenEmbeddingFunction()


class VectorMemoryManager:
    """Manages semantic vector storage for study notes using ChromaDB + Qwen embeddings."""

    def __init__(self):
        self._embedding_fn = QwenEmbeddingFunction()
        self._client = chromadb.PersistentClient(path=CHROMA_PATH)
        self._collection = self._client.get_or_create_collection(
            name="study_notes",
            embedding_function=self._embedding_fn,
        )
        print(f"VectorMemoryManager: collection 'study_notes' ready ({self.get_collection_count()} notes stored).")

    def add_note(self, session_id: str, topic: str, concepts: list, text: str, student_id: str = DEFAULT_STUDENT_ID) -> dict:
        """Embed and store a study note with scoped metadata."""
        try:
            student_id = str(student_id or DEFAULT_STUDENT_ID).strip() or DEFAULT_STUDENT_ID
            note_id = str(uuid4())
            self._collection.add(
                ids=[note_id],
                documents=[text],
                metadatas=[{
                    "student_id": student_id,
                    "session_id": session_id,
                    "topic": topic,
                    "concepts": ",".join(concepts),
                    "date": date.today().isoformat(),
                }],
            )
            return {"success": True, "id": note_id}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def semantic_search(self, query: str, n_results: int = 5, student_id: str = DEFAULT_STUDENT_ID) -> dict:
        """Find the most semantically similar scoped notes to a query string."""
        try:
            student_id = str(student_id or DEFAULT_STUDENT_ID).strip() or DEFAULT_STUDENT_ID
            results = self._collection.query(
                query_texts=[query],
                n_results=n_results,
                where={"student_id": student_id},
            )
            # ChromaDB cosine distance: 0 = identical, 2 = opposite. similarity = 1 - distance.
            ids = results["ids"][0]
            documents = results["documents"][0]
            distances = results["distances"][0]
            metadatas = results["metadatas"][0]

            formatted = []
            for i in range(len(ids)):
                formatted.append({
                    "text": documents[i],
                    "topic": metadatas[i].get("topic", ""),
                    "concepts": metadatas[i].get("concepts", ""),
                    "date": metadatas[i].get("date", ""),
                    "student_id": metadatas[i].get("student_id", DEFAULT_STUDENT_ID),
                    "similarity_score": round(1 - distances[i], 4),
                })

            return {"success": True, "results": formatted}
        except Exception as e:
            return {"success": False, "error": str(e), "results": []}

    def get_related_concepts(self, concept_name: str, n_results: int = 5, student_id: str = DEFAULT_STUDENT_ID) -> dict:
        """Find scoped notes semantically related to a given concept name."""
        return self.semantic_search(query=concept_name, n_results=n_results, student_id=student_id)

    def get_collection_count(self) -> int:
        """Return the total number of notes stored in the collection."""
        return self._collection.count()
