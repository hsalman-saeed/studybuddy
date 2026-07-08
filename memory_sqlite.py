"""Structured SQLite memory layer for persistent, queryable knowledge storage."""

import sqlite3
import json
from datetime import date

from config import DB_PATH


class MemoryManager:
    """Manages all structured (non-vector) persistent storage using SQLite."""

    def __init__(self):
        self._init_tables()

    def _get_conn(self):
        return sqlite3.connect(DB_PATH)

    def _init_tables(self):
        conn = self._get_conn()
        try:
            c = conn.cursor()

            c.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_date TEXT,
                    topic TEXT NOT NULL,
                    concepts_learned TEXT,
                    difficulty_rating INTEGER,
                    notes TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            c.execute("""
                CREATE TABLE IF NOT EXISTS concepts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    concept_name TEXT UNIQUE NOT NULL,
                    subject TEXT,
                    mastery_level INTEGER DEFAULT 0,
                    times_studied INTEGER DEFAULT 0,
                    times_correct INTEGER DEFAULT 0,
                    times_wrong INTEGER DEFAULT 0,
                    last_studied TEXT,
                    next_review_date TEXT,
                    ease_factor REAL DEFAULT 2.5,
                    interval_days INTEGER DEFAULT 1,
                    review_count INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            c.execute("""
                CREATE TABLE IF NOT EXISTS quiz_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    topic TEXT NOT NULL,
                    question TEXT NOT NULL,
                    correct_answer TEXT NOT NULL,
                    student_answer TEXT,
                    is_correct INTEGER,
                    quiz_date TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            c.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            conn.commit()
            print("MemoryManager: 4 tables initialized successfully.")
        except Exception as e:
            print(f"MemoryManager: table init failed — {e}")
        finally:
            conn.close()

    # ── Sessions ────────────────────────────────────────────────────────

    def save_study_session(self, topic, concepts_learned: list, difficulty_rating=3, notes=""):
        """Insert a study session and upsert each concept into the concepts table."""
        conn = self._get_conn()
        try:
            c = conn.cursor()
            today = date.today().isoformat()

            c.execute(
                "INSERT INTO sessions (session_date, topic, concepts_learned, difficulty_rating, notes) "
                "VALUES (?, ?, ?, ?, ?)",
                (today, topic, json.dumps(concepts_learned), difficulty_rating, notes),
            )

            for concept in concepts_learned:
                c.execute(
                    "SELECT id, times_studied FROM concepts WHERE concept_name = ?",
                    (concept,),
                )
                existing = c.fetchone()
                if existing:
                    c.execute(
                        "UPDATE concepts SET times_studied = times_studied + 1, last_studied = ? "
                        "WHERE concept_name = ?",
                        (today, concept),
                    )
                else:
                    c.execute(
                        "INSERT INTO concepts (concept_name, subject, mastery_level, times_studied, "
                        "last_studied) VALUES (?, ?, 0, 1, ?)",
                        (concept, topic, today),
                    )

            conn.commit()
            return {"success": True, "message": f"Session saved for '{topic}' with {len(concepts_learned)} concept(s)."}
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            conn.close()

    def get_study_history(self, topic=None, limit=20):
        """Return recent study sessions, optionally filtered by topic (LIKE match)."""
        conn = self._get_conn()
        try:
            c = conn.cursor()
            if topic:
                c.execute(
                    "SELECT id, session_date, topic, concepts_learned, difficulty_rating, notes, created_at "
                    "FROM sessions WHERE topic LIKE ? ORDER BY session_date DESC LIMIT ?",
                    (f"%{topic}%", limit),
                )
            else:
                c.execute(
                    "SELECT id, session_date, topic, concepts_learned, difficulty_rating, notes, created_at "
                    "FROM sessions ORDER BY session_date DESC LIMIT ?",
                    (limit,),
                )
            rows = c.fetchall()
            sessions = []
            for row in rows:
                sessions.append({
                    "id": row[0],
                    "session_date": row[1],
                    "topic": row[2],
                    "concepts_learned": json.loads(row[3]) if row[3] else [],
                    "difficulty_rating": row[4],
                    "notes": row[5],
                    "created_at": row[6],
                })
            return {"success": True, "sessions": sessions}
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            conn.close()

    # ── Concepts ────────────────────────────────────────────────────────

    def update_concept_mastery(self, concept_name, is_correct: bool):
        """Adjust mastery_level by ±1 based on correctness, clamped to 0–10."""
        conn = self._get_conn()
        try:
            c = conn.cursor()
            if is_correct:
                c.execute(
                    "UPDATE concepts SET times_correct = times_correct + 1, "
                    "mastery_level = MIN(mastery_level + 1, 10) "
                    "WHERE concept_name = ?",
                    (concept_name,),
                )
            else:
                c.execute(
                    "UPDATE concepts SET times_wrong = times_wrong + 1, "
                    "mastery_level = MAX(mastery_level - 1, 0) "
                    "WHERE concept_name = ?",
                    (concept_name,),
                )
            conn.commit()
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            conn.close()

    def get_weak_areas(self, limit=10):
        """Return concepts ranked by lowest mastery and most wrong answers."""
        conn = self._get_conn()
        try:
            c = conn.cursor()
            c.execute(
                "SELECT concept_name, subject, mastery_level, times_studied, "
                "times_correct, times_wrong, last_studied, next_review_date "
                "FROM concepts ORDER BY mastery_level ASC, times_wrong DESC LIMIT ?",
                (limit,),
            )
            rows = c.fetchall()
            weak = []
            for row in rows:
                weak.append({
                    "concept_name": row[0],
                    "subject": row[1],
                    "mastery_level": row[2],
                    "times_studied": row[3],
                    "times_correct": row[4],
                    "times_wrong": row[5],
                    "last_studied": row[6],
                    "next_review_date": row[7],
                })
            return {"success": True, "weak_areas": weak}
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            conn.close()

    def get_concepts_due_for_review(self):
        """Return concepts where next_review_date is set and <= today."""
        conn = self._get_conn()
        try:
            c = conn.cursor()
            today = date.today().isoformat()
            c.execute(
                "SELECT concept_name, subject, mastery_level, next_review_date, "
                "ease_factor, interval_days, review_count "
                "FROM concepts WHERE next_review_date IS NOT NULL AND next_review_date <= ? "
                "ORDER BY next_review_date ASC",
                (today,),
            )
            rows = c.fetchall()
            due = []
            for row in rows:
                due.append({
                    "concept_name": row[0],
                    "subject": row[1],
                    "mastery_level": row[2],
                    "next_review_date": row[3],
                    "ease_factor": row[4],
                    "interval_days": row[5],
                    "review_count": row[6],
                })
            return {"success": True, "due": due}
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            conn.close()

    # ── Quiz results ────────────────────────────────────────────────────

    def save_quiz_result(self, topic, question, correct_answer, student_answer, is_correct):
        """Save a quiz result and update concept mastery for the matching concept."""
        conn = self._get_conn()
        try:
            c = conn.cursor()
            today = date.today().isoformat()

            c.execute(
                "INSERT INTO quiz_results (topic, question, correct_answer, student_answer, is_correct, quiz_date) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (topic, question, correct_answer, student_answer, int(is_correct), today),
            )
            conn.commit()

            self.update_concept_mastery(topic, is_correct)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            conn.close()

    # ── Conversations ───────────────────────────────────────────────────

    def save_conversation_turn(self, session_id, role, content):
        """Persist one conversation turn. Fails silently with a printed warning."""
        conn = self._get_conn()
        try:
            c = conn.cursor()
            c.execute(
                "INSERT INTO conversations (session_id, role, content) VALUES (?, ?, ?)",
                (session_id, role, content),
            )
            conn.commit()
        except Exception as e:
            print(f"MemoryManager warning: failed to save conversation turn — {e}")
        finally:
            conn.close()

    def get_conversation_history(self, session_id=None, limit=10):
        """Return recent conversation messages, optionally filtered by session_id."""
        conn = self._get_conn()
        try:
            c = conn.cursor()
            if session_id:
                c.execute(
                    "SELECT id, session_id, role, content, timestamp "
                    "FROM conversations WHERE session_id = ? ORDER BY timestamp DESC LIMIT ?",
                    (session_id, limit),
                )
            else:
                c.execute(
                    "SELECT id, session_id, role, content, timestamp "
                    "FROM conversations ORDER BY timestamp DESC LIMIT ?",
                    (limit,),
                )
            rows = c.fetchall()
            return [
                {
                    "id": row[0],
                    "session_id": row[1],
                    "role": row[2],
                    "content": row[3],
                    "timestamp": row[4],
                }
                for row in rows
            ]
        except Exception as e:
            print(f"MemoryManager warning: failed to get conversation history — {e}")
            return []
        finally:
            conn.close()

    # ── Aggregate queries ───────────────────────────────────────────────

    def get_concept(self, concept_name: str) -> dict:
        """Return the full row for a concept as a dict, or {"error": "concept not found"}."""
        conn = self._get_conn()
        try:
            c = conn.cursor()
            c.execute(
                "SELECT concept_name, subject, mastery_level, times_studied, "
                "times_correct, times_wrong, last_studied, next_review_date, "
                "ease_factor, interval_days, review_count "
                "FROM concepts WHERE concept_name = ?",
                (concept_name,),
            )
            row = c.fetchone()
            if row is None:
                return {"error": "concept not found"}
            return {
                "concept_name": row[0],
                "subject": row[1],
                "mastery_level": row[2],
                "times_studied": row[3],
                "times_correct": row[4],
                "times_wrong": row[5],
                "last_studied": row[6],
                "next_review_date": row[7],
                "ease_factor": row[8],
                "interval_days": row[9],
                "review_count": row[10],
            }
        except Exception as e:
            return {"error": str(e)}
        finally:
            conn.close()

    def update_review_schedule(
        self,
        concept_name: str,
        ease_factor: float,
        interval_days: int,
        next_review_date: str,
        review_count: int,
    ) -> dict:
        """UPDATE the concepts table row for concept_name with the 4 scheduling values."""
        conn = self._get_conn()
        try:
            c = conn.cursor()
            c.execute(
                "UPDATE concepts SET ease_factor = ?, interval_days = ?, "
                "next_review_date = ?, review_count = ? WHERE concept_name = ?",
                (ease_factor, interval_days, next_review_date, review_count, concept_name),
            )
            if c.rowcount == 0:
                return {"success": False, "error": "concept not found"}
            conn.commit()
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            conn.close()

    def get_all_studied_topics(self):
        """Return a list of distinct topic strings from sessions."""
        conn = self._get_conn()
        try:
            c = conn.cursor()
            c.execute("SELECT DISTINCT topic FROM sessions ORDER BY topic")
            return [row[0] for row in c.fetchall()]
        except Exception as e:
            print(f"MemoryManager warning: failed to get topics — {e}")
            return []
        finally:
            conn.close()

    def get_overall_stats(self):
        """Return aggregate stats across sessions, topics, and quiz results."""
        conn = self._get_conn()
        try:
            c = conn.cursor()

            c.execute("SELECT COUNT(*) FROM sessions")
            total_sessions = c.fetchone()[0]

            c.execute("SELECT COUNT(DISTINCT topic) FROM sessions")
            total_topics = c.fetchone()[0]

            c.execute("SELECT COUNT(*) FROM quiz_results")
            total_quiz_questions = c.fetchone()[0]

            c.execute("SELECT COUNT(*) FROM quiz_results WHERE is_correct = 1")
            correct_answers = c.fetchone()[0]

            accuracy = (
                round((correct_answers / total_quiz_questions) * 100, 1)
                if total_quiz_questions > 0
                else 0.0
            )

            return {
                "total_sessions": total_sessions,
                "total_topics": total_topics,
                "total_quiz_questions": total_quiz_questions,
                "overall_accuracy": accuracy,
            }
        except Exception as e:
            return {"error": str(e)}
        finally:
            conn.close()

    def get_all_concepts_with_details(self) -> list:
        """Return all concepts with full detail fields, ordered by mastery ASC."""
        conn = self._get_conn()
        try:
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute("""
                SELECT concept_name, subject, mastery_level, times_studied,
                       times_correct, times_wrong, last_studied, next_review_date
                FROM concepts
                ORDER BY mastery_level ASC
            """)
            return [dict(row) for row in c.fetchall()]
        except Exception as e:
            print(f"MemoryManager warning: failed to get concepts — {e}")
            return []
        finally:
            conn.close()

    def get_quiz_history_chronological(self, limit: int = 200) -> list:
        """Return quiz results in chronological order with topic, correctness, date."""
        conn = self._get_conn()
        try:
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute("""
                SELECT topic, is_correct, quiz_date
                FROM quiz_results
                ORDER BY quiz_date ASC
                LIMIT ?
            """, (limit,))
            return [dict(row) for row in c.fetchall()]
        except Exception as e:
            print(f"MemoryManager warning: failed to get quiz history — {e}")
            return []
        finally:
            conn.close()

    def get_all_session_dates(self) -> list:
        """Return distinct session dates (YYYY-MM-DD) in ascending order."""
        conn = self._get_conn()
        try:
            c = conn.cursor()
            c.execute("""
                SELECT DISTINCT date(session_date) FROM sessions
                ORDER BY session_date ASC
            """)
            return [row[0] for row in c.fetchall() if row[0]]
        except Exception as e:
            print(f"MemoryManager warning: failed to get session dates — {e}")
            return []
        finally:
            conn.close()
