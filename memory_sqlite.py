"""Structured SQLite memory layer for persistent, queryable knowledge storage."""

import sqlite3
import json
from datetime import date, timedelta

from config import DB_PATH


DEFAULT_STUDENT_ID = "demo_student"


class MemoryManager:
    """Manages all structured (non-vector) persistent storage using SQLite."""

    def __init__(self):
        self._init_tables()

    def _get_conn(self):
        return sqlite3.connect(DB_PATH)

    def _normalize_student_id(self, student_id=None):
        """Return a safe profile scope for all persisted learner data."""
        cleaned = str(student_id or DEFAULT_STUDENT_ID).strip()
        return cleaned or DEFAULT_STUDENT_ID

    def _table_columns(self, cursor, table_name: str) -> set:
        cursor.execute(f"PRAGMA table_info({table_name})")
        return {row[1] for row in cursor.fetchall()}

    def _concepts_needs_rebuild(self, cursor) -> bool:
        columns = self._table_columns(cursor, "concepts")
        if "student_id" not in columns:
            return True

        cursor.execute("PRAGMA index_list(concepts)")
        indexes = cursor.fetchall()
        for index in indexes:
            index_name = index[1]
            is_unique = bool(index[2])
            if not is_unique:
                continue
            cursor.execute(f"PRAGMA index_info({index_name})")
            indexed_columns = [row[2] for row in cursor.fetchall()]
            if indexed_columns == ["concept_name"]:
                return True
        return False

    def _migrate_tables(self, cursor):
        """Add profile scoping to existing installs without losing demo data."""
        for table_name in ("sessions", "quiz_results", "conversations"):
            columns = self._table_columns(cursor, table_name)
            if "student_id" not in columns:
                cursor.execute(
                    f"ALTER TABLE {table_name} "
                    f"ADD COLUMN student_id TEXT DEFAULT '{DEFAULT_STUDENT_ID}'"
                )

        if self._concepts_needs_rebuild(cursor):
            columns = self._table_columns(cursor, "concepts")
            cursor.execute("ALTER TABLE concepts RENAME TO concepts_old")
            cursor.execute("""
                CREATE TABLE concepts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    student_id TEXT NOT NULL DEFAULT 'demo_student',
                    concept_name TEXT NOT NULL,
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
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(student_id, concept_name)
                )
            """)
            student_expr = "student_id" if "student_id" in columns else f"'{DEFAULT_STUDENT_ID}'"
            cursor.execute(f"""
                INSERT OR IGNORE INTO concepts (
                    id, student_id, concept_name, subject, mastery_level,
                    times_studied, times_correct, times_wrong, last_studied,
                    next_review_date, ease_factor, interval_days, review_count, created_at
                )
                SELECT id, {student_expr}, concept_name, subject, mastery_level,
                       times_studied, times_correct, times_wrong, last_studied,
                       next_review_date, ease_factor, interval_days, review_count, created_at
                FROM concepts_old
            """)
            cursor.execute("DROP TABLE concepts_old")

    def _init_tables(self):
        conn = self._get_conn()
        try:
            c = conn.cursor()

            c.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    student_id TEXT NOT NULL DEFAULT 'demo_student',
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
                    student_id TEXT NOT NULL DEFAULT 'demo_student',
                    concept_name TEXT NOT NULL,
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
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(student_id, concept_name)
                )
            """)

            c.execute("""
                CREATE TABLE IF NOT EXISTS quiz_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    student_id TEXT NOT NULL DEFAULT 'demo_student',
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
                    student_id TEXT NOT NULL DEFAULT 'demo_student',
                    session_id TEXT,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            c.execute("""
                CREATE TABLE IF NOT EXISTS learning_paths (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    student_id TEXT NOT NULL,
                    goal TEXT NOT NULL,
                    plan_text TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            c.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    salt TEXT NOT NULL,
                    display_name TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            self._migrate_tables(c)
            conn.commit()
            print("MemoryManager: 6 tables initialized successfully.")
        except Exception as e:
            print(f"MemoryManager: table init failed — {e}")
        finally:
            conn.close()

    def seed_demo_data_if_empty(self, student_id=DEFAULT_STUDENT_ID):
        """Populate a fresh database with realistic data for reliable demos."""
        student_id = self._normalize_student_id(student_id)
        if not self.user_exists("demo_student"):
            self.create_user("demo_student", "demo123")
        conn = self._get_conn()
        try:
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM sessions")
            if c.fetchone()[0] > 0:
                return {"success": True, "seeded": False, "message": "Existing sessions found; demo seed skipped."}

            today = date.today()
            sessions = [
                (
                    student_id,
                    (today - timedelta(days=5)).isoformat(),
                    "Python Functions",
                    ["function parameters", "return values", "scope"],
                    3,
                    "Practiced defining reusable functions, passing arguments, returning values, and reading local vs global scope.",
                ),
                (
                    student_id,
                    (today - timedelta(days=2)).isoformat(),
                    "Algebra Linear Equations",
                    ["isolating variables", "inverse operations", "checking solutions"],
                    4,
                    "Solved one-step and two-step equations, then checked answers by substitution.",
                ),
                (
                    student_id,
                    today.isoformat(),
                    "Biology Cell Structure",
                    ["cell membrane", "nucleus", "mitochondria"],
                    2,
                    "Reviewed organelle functions with emphasis on the nucleus storing DNA and mitochondria producing ATP.",
                ),
            ]

            for row in sessions:
                c.execute(
                    "INSERT INTO sessions (student_id, session_date, topic, concepts_learned, difficulty_rating, notes) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (row[0], row[1], row[2], json.dumps(row[3]), row[4], row[5]),
                )

            concepts = [
                (student_id, "function parameters", "Python Functions", 5, 1, 1, 0, (today - timedelta(days=5)).isoformat(), (today + timedelta(days=3)).isoformat(), 2.5, 6, 2),
                (student_id, "return values", "Python Functions", 4, 1, 1, 0, (today - timedelta(days=5)).isoformat(), (today + timedelta(days=1)).isoformat(), 2.5, 1, 1),
                (student_id, "scope", "Python Functions", 2, 1, 0, 1, (today - timedelta(days=5)).isoformat(), today.isoformat(), 2.36, 1, 0),
                (student_id, "isolating variables", "Algebra Linear Equations", 3, 1, 0, 1, (today - timedelta(days=2)).isoformat(), today.isoformat(), 2.36, 1, 0),
                (student_id, "inverse operations", "Algebra Linear Equations", 4, 1, 1, 0, (today - timedelta(days=2)).isoformat(), (today + timedelta(days=1)).isoformat(), 2.5, 1, 1),
                (student_id, "checking solutions", "Algebra Linear Equations", 1, 1, 0, 1, (today - timedelta(days=2)).isoformat(), today.isoformat(), 2.36, 1, 0),
                (student_id, "cell membrane", "Biology Cell Structure", 3, 1, 1, 1, today.isoformat(), (today + timedelta(days=1)).isoformat(), 2.5, 1, 1),
                (student_id, "nucleus", "Biology Cell Structure", 5, 1, 1, 0, today.isoformat(), (today + timedelta(days=6)).isoformat(), 2.5, 6, 2),
                (student_id, "mitochondria", "Biology Cell Structure", 2, 1, 0, 1, today.isoformat(), today.isoformat(), 2.36, 1, 0),
            ]
            c.executemany(
                "INSERT OR IGNORE INTO concepts (student_id, concept_name, subject, mastery_level, times_studied, "
                "times_correct, times_wrong, last_studied, next_review_date, ease_factor, interval_days, review_count) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                concepts,
            )

            quiz_results = [
                (student_id, "function parameters", "What is the purpose of a function parameter?", "It lets a function receive input values.", "It passes information into the function.", 1, (today - timedelta(days=5)).isoformat()),
                (student_id, "scope", "Can a local variable be used outside its function?", "No, local variables are scoped to the function.", "Yes, if it was assigned once.", 0, (today - timedelta(days=4)).isoformat()),
                (student_id, "inverse operations", "How do you solve x + 7 = 12?", "Subtract 7 from both sides, so x = 5.", "Subtract 7 from both sides.", 1, (today - timedelta(days=2)).isoformat()),
                (student_id, "checking solutions", "How do you verify x = 5 solves x + 7 = 12?", "Substitute 5 for x and confirm 5 + 7 = 12.", "Divide both sides by 5.", 0, (today - timedelta(days=1)).isoformat()),
                (student_id, "nucleus", "What does the nucleus contain?", "DNA/genetic instructions.", "DNA", 1, today.isoformat()),
                (student_id, "mitochondria", "What is the main job of mitochondria?", "Producing ATP energy for the cell.", "Storing DNA", 0, today.isoformat()),
            ]
            c.executemany(
                "INSERT INTO quiz_results (student_id, topic, question, correct_answer, student_answer, is_correct, quiz_date) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                quiz_results,
            )

            conn.commit()
            return {"success": True, "seeded": True, "message": "Seeded demo study history for a fresh database."}
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            conn.close()

    # ── Sessions ────────────────────────────────────────────────────────

    def save_study_session(self, topic, concepts_learned: list, difficulty_rating=3, notes="", student_id=DEFAULT_STUDENT_ID):
        """Insert a study session and upsert each concept into the scoped concepts table."""
        student_id = self._normalize_student_id(student_id)
        conn = self._get_conn()
        try:
            c = conn.cursor()
            today = date.today().isoformat()

            c.execute(
                "INSERT INTO sessions (student_id, session_date, topic, concepts_learned, difficulty_rating, notes) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (student_id, today, topic, json.dumps(concepts_learned), difficulty_rating, notes),
            )

            for concept in concepts_learned:
                c.execute(
                    "SELECT id, times_studied FROM concepts WHERE student_id = ? AND concept_name = ?",
                    (student_id, concept),
                )
                existing = c.fetchone()
                if existing:
                    c.execute(
                        "UPDATE concepts SET times_studied = times_studied + 1, last_studied = ? "
                        "WHERE student_id = ? AND concept_name = ?",
                        (today, student_id, concept),
                    )
                else:
                    c.execute(
                        "INSERT INTO concepts (student_id, concept_name, subject, mastery_level, times_studied, "
                        "last_studied) VALUES (?, ?, ?, 0, 1, ?)",
                        (student_id, concept, topic, today),
                    )

            conn.commit()
            return {"success": True, "message": f"Session saved for '{topic}' with {len(concepts_learned)} concept(s)."}
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            conn.close()

    def get_study_history(self, topic=None, limit=20, student_id=DEFAULT_STUDENT_ID):
        """Return recent scoped study sessions, optionally filtered by topic."""
        student_id = self._normalize_student_id(student_id)
        conn = self._get_conn()
        try:
            c = conn.cursor()
            if topic:
                c.execute(
                    "SELECT id, student_id, session_date, topic, concepts_learned, difficulty_rating, notes, created_at "
                    "FROM sessions WHERE student_id = ? AND topic LIKE ? ORDER BY session_date DESC LIMIT ?",
                    (student_id, f"%{topic}%", limit),
                )
            else:
                c.execute(
                    "SELECT id, student_id, session_date, topic, concepts_learned, difficulty_rating, notes, created_at "
                    "FROM sessions WHERE student_id = ? ORDER BY session_date DESC LIMIT ?",
                    (student_id, limit),
                )
            rows = c.fetchall()
            sessions = []
            for row in rows:
                sessions.append({
                    "id": row[0],
                    "student_id": row[1],
                    "session_date": row[2],
                    "topic": row[3],
                    "concepts_learned": json.loads(row[4]) if row[4] else [],
                    "difficulty_rating": row[5],
                    "notes": row[6],
                    "created_at": row[7],
                })
            return {"success": True, "sessions": sessions}
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            conn.close()

    # ── Concepts ────────────────────────────────────────────────────────

    def update_concept_mastery(self, concept_name, is_correct: bool, student_id=DEFAULT_STUDENT_ID):
        """Adjust mastery_level by +/-1 based on correctness, clamped to 0-10."""
        student_id = self._normalize_student_id(student_id)
        conn = self._get_conn()
        try:
            c = conn.cursor()
            if is_correct:
                c.execute(
                    "UPDATE concepts SET times_correct = times_correct + 1, "
                    "mastery_level = MIN(mastery_level + 1, 10) "
                    "WHERE student_id = ? AND concept_name = ?",
                    (student_id, concept_name),
                )
            else:
                c.execute(
                    "UPDATE concepts SET times_wrong = times_wrong + 1, "
                    "mastery_level = MAX(mastery_level - 1, 0) "
                    "WHERE student_id = ? AND concept_name = ?",
                    (student_id, concept_name),
                )
            conn.commit()
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            conn.close()

    def get_weak_areas(self, limit=10, student_id=DEFAULT_STUDENT_ID):
        """Return scoped concepts ranked by lowest mastery and most wrong answers."""
        student_id = self._normalize_student_id(student_id)
        conn = self._get_conn()
        try:
            c = conn.cursor()
            c.execute(
                "SELECT concept_name, subject, mastery_level, times_studied, "
                "times_correct, times_wrong, last_studied, next_review_date "
                "FROM concepts WHERE student_id = ? "
                "ORDER BY mastery_level ASC, times_wrong DESC LIMIT ?",
                (student_id, limit),
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

    def get_concepts_due_for_review(self, student_id=DEFAULT_STUDENT_ID):
        """Return scoped concepts where next_review_date is set and <= today."""
        student_id = self._normalize_student_id(student_id)
        conn = self._get_conn()
        try:
            c = conn.cursor()
            today = date.today().isoformat()
            c.execute(
                "SELECT concept_name, subject, mastery_level, next_review_date, "
                "ease_factor, interval_days, review_count "
                "FROM concepts WHERE student_id = ? AND next_review_date IS NOT NULL AND next_review_date <= ? "
                "ORDER BY next_review_date ASC",
                (student_id, today),
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

    def save_quiz_result(self, topic, question, correct_answer, student_answer, is_correct, student_id=DEFAULT_STUDENT_ID):
        """Save a quiz result and update concept mastery for the matching scoped concept."""
        student_id = self._normalize_student_id(student_id)
        conn = self._get_conn()
        try:
            c = conn.cursor()
            today = date.today().isoformat()

            c.execute(
                "INSERT INTO quiz_results (student_id, topic, question, correct_answer, student_answer, is_correct, quiz_date) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (student_id, topic, question, correct_answer, student_answer, int(is_correct), today),
            )
            conn.commit()

            self.update_concept_mastery(topic, is_correct, student_id=student_id)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            conn.close()

    # ── Conversations ───────────────────────────────────────────────────

    def save_conversation_turn(self, session_id, role, content, student_id=DEFAULT_STUDENT_ID):
        """Persist one scoped conversation turn. Fails silently with a printed warning."""
        student_id = self._normalize_student_id(student_id)
        conn = self._get_conn()
        try:
            c = conn.cursor()
            c.execute(
                "INSERT INTO conversations (student_id, session_id, role, content) VALUES (?, ?, ?, ?)",
                (student_id, session_id, role, content),
            )
            conn.commit()
        except Exception as e:
            print(f"MemoryManager warning: failed to save conversation turn — {e}")
        finally:
            conn.close()

    def get_conversation_history(self, session_id=None, limit=10, student_id=DEFAULT_STUDENT_ID):
        """Return recent scoped conversation messages, optionally filtered by session_id."""
        student_id = self._normalize_student_id(student_id)
        conn = self._get_conn()
        try:
            c = conn.cursor()
            if session_id:
                c.execute(
                    "SELECT id, session_id, role, content, timestamp "
                    "FROM conversations WHERE student_id = ? AND session_id = ? ORDER BY timestamp DESC LIMIT ?",
                    (student_id, session_id, limit),
                )
            else:
                c.execute(
                    "SELECT id, session_id, role, content, timestamp "
                    "FROM conversations WHERE student_id = ? ORDER BY timestamp DESC LIMIT ?",
                    (student_id, limit),
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

    # ── Learning Paths ──────────────────────────────────────────────────

    def save_learning_path(self, student_id, goal, plan_text):
        """Save a generated learning path."""
        student_id = self._normalize_student_id(student_id)
        conn = self._get_conn()
        try:
            c = conn.cursor()
            c.execute(
                "INSERT INTO learning_paths (student_id, goal, plan_text) VALUES (?, ?, ?)",
                (student_id, goal, plan_text),
            )
            conn.commit()
            return {"success": True, "id": c.lastrowid}
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            conn.close()

    def get_learning_paths(self, student_id, limit=10):
        """Retrieve saved learning paths for a student, newest first."""
        student_id = self._normalize_student_id(student_id)
        conn = self._get_conn()
        try:
            c = conn.cursor()
            c.execute(
                "SELECT id, goal, plan_text, created_at FROM learning_paths WHERE student_id = ? ORDER BY created_at DESC LIMIT ?",
                (student_id, limit),
            )
            rows = c.fetchall()
            return [{"id": r[0], "goal": r[1], "plan_text": r[2], "created_at": r[3]} for r in rows]
        finally:
            conn.close()

    # ── Aggregate queries ───────────────────────────────────────────────

    def get_concept(self, concept_name: str, student_id=DEFAULT_STUDENT_ID) -> dict:
        """Return the full scoped concept row, or {"error": "concept not found"}."""
        student_id = self._normalize_student_id(student_id)
        conn = self._get_conn()
        try:
            c = conn.cursor()
            c.execute(
                "SELECT concept_name, subject, mastery_level, times_studied, "
                "times_correct, times_wrong, last_studied, next_review_date, "
                "ease_factor, interval_days, review_count "
                "FROM concepts WHERE student_id = ? AND concept_name = ?",
                (student_id, concept_name),
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
        student_id=DEFAULT_STUDENT_ID,
    ) -> dict:
        """UPDATE the scoped concepts table row with the scheduling values."""
        student_id = self._normalize_student_id(student_id)
        conn = self._get_conn()
        try:
            c = conn.cursor()
            c.execute(
                "UPDATE concepts SET ease_factor = ?, interval_days = ?, "
                "next_review_date = ?, review_count = ? WHERE student_id = ? AND concept_name = ?",
                (ease_factor, interval_days, next_review_date, review_count, student_id, concept_name),
            )
            if c.rowcount == 0:
                return {"success": False, "error": "concept not found"}
            conn.commit()
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            conn.close()

    def get_all_studied_topics(self, student_id=DEFAULT_STUDENT_ID):
        """Return scoped distinct topic strings from sessions."""
        student_id = self._normalize_student_id(student_id)
        conn = self._get_conn()
        try:
            c = conn.cursor()
            c.execute(
                "SELECT DISTINCT topic FROM sessions WHERE student_id = ? ORDER BY topic",
                (student_id,),
            )
            return [row[0] for row in c.fetchall()]
        except Exception as e:
            print(f"MemoryManager warning: failed to get topics — {e}")
            return []
        finally:
            conn.close()

    def get_overall_stats(self, student_id=DEFAULT_STUDENT_ID):
        """Return scoped aggregate stats across sessions, topics, and quiz results."""
        student_id = self._normalize_student_id(student_id)
        conn = self._get_conn()
        try:
            c = conn.cursor()

            c.execute("SELECT COUNT(*) FROM sessions WHERE student_id = ?", (student_id,))
            total_sessions = c.fetchone()[0]

            c.execute("SELECT COUNT(DISTINCT topic) FROM sessions WHERE student_id = ?", (student_id,))
            total_topics = c.fetchone()[0]

            c.execute("SELECT COUNT(*) FROM quiz_results WHERE student_id = ?", (student_id,))
            total_quiz_questions = c.fetchone()[0]

            c.execute(
                "SELECT COUNT(*) FROM quiz_results WHERE student_id = ? AND is_correct = 1",
                (student_id,),
            )
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

    def get_all_concepts_with_details(self, student_id=DEFAULT_STUDENT_ID) -> list:
        """Return scoped concepts with full detail fields, ordered by mastery ASC."""
        student_id = self._normalize_student_id(student_id)
        conn = self._get_conn()
        try:
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute("""
                SELECT concept_name, subject, mastery_level, times_studied,
                       times_correct, times_wrong, last_studied, next_review_date
                FROM concepts
                WHERE student_id = ?
                ORDER BY mastery_level ASC
            """, (student_id,))
            return [dict(row) for row in c.fetchall()]
        except Exception as e:
            print(f"MemoryManager warning: failed to get concepts — {e}")
            return []
        finally:
            conn.close()

    def get_quiz_history_chronological(self, limit: int = 200, student_id=DEFAULT_STUDENT_ID) -> list:
        """Return scoped quiz results in chronological order with topic, correctness, date."""
        student_id = self._normalize_student_id(student_id)
        conn = self._get_conn()
        try:
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute("""
                SELECT topic, is_correct, quiz_date
                FROM quiz_results
                WHERE student_id = ?
                ORDER BY quiz_date ASC
                LIMIT ?
            """, (student_id, limit))
            return [dict(row) for row in c.fetchall()]
        except Exception as e:
            print(f"MemoryManager warning: failed to get quiz history — {e}")
            return []
        finally:
            conn.close()

    def get_all_session_dates(self, student_id=DEFAULT_STUDENT_ID) -> list:
        """Return scoped distinct session dates (YYYY-MM-DD) in ascending order."""
        student_id = self._normalize_student_id(student_id)
        conn = self._get_conn()
        try:
            c = conn.cursor()
            c.execute("""
                SELECT DISTINCT date(session_date) FROM sessions
                WHERE student_id = ?
                ORDER BY session_date ASC
            """, (student_id,))
            return [row[0] for row in c.fetchall() if row[0]]
        except Exception as e:
            print(f"MemoryManager warning: failed to get session dates — {e}")
            return []
        finally:
            conn.close()

    # ── Users / Auth ─────────────────────────────────────────────────────

    def create_user(self, username, password):
        """Create a new user with hashed password. Returns dict with success status."""
        import hashlib, os
        salt = os.urandom(32)
        password_hash = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)
        conn = self._get_conn()
        try:
            c = conn.cursor()
            c.execute(
                "INSERT INTO users (username, password_hash, salt, display_name) VALUES (?, ?, ?, ?)",
                (username, password_hash.hex(), salt.hex(), username)
            )
            conn.commit()
            return {"success": True, "username": username}
        except sqlite3.IntegrityError:
            return {"success": False, "error": "Username already exists"}
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            conn.close()

    def authenticate_user(self, username, password):
        """Verify username and password. Returns True if valid."""
        import hashlib
        conn = self._get_conn()
        try:
            c = conn.cursor()
            c.execute("SELECT password_hash, salt FROM users WHERE username = ?", (username,))
            row = c.fetchone()
            if not row:
                return False
            stored_hash, salt = row
            computed_hash = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), bytes.fromhex(salt), 100000)
            return computed_hash.hex() == stored_hash
        finally:
            conn.close()

    def user_exists(self, username):
        """Check if a username is already registered."""
        conn = self._get_conn()
        try:
            c = conn.cursor()
            c.execute("SELECT 1 FROM users WHERE username = ?", (username,))
            return c.fetchone() is not None
        finally:
            conn.close()
