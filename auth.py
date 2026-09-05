"""Authentication module for StudyBuddy."""

import re
from memory_sqlite import MemoryManager

_memory = MemoryManager()


def signup(username, password, confirm_password):
    """Register a new user. Returns (success: bool, message: str)."""
    # Validate username
    if not username or len(username.strip()) < 3:
        return False, "Username must be at least 3 characters."
    if len(username.strip()) > 30:
        return False, "Username must be 30 characters or fewer."
    if not re.match(r'^[a-zA-Z0-9_]+$', username.strip()):
        return False, "Username can only contain letters, numbers, and underscores."

    # Validate password
    if not password or len(password) < 6:
        return False, "Password must be at least 6 characters."
    if password != confirm_password:
        return False, "Passwords do not match."

    username = username.strip().lower()
    result = _memory.create_user(username, password)
    if result.get("success"):
        return True, f"Account created! Welcome, {username}."
    return False, result.get("error", "Signup failed.")


def login(username, password):
    """Authenticate a user. Returns (success: bool, student_id: str, message: str)."""
    if not username or not password:
        return False, "", "Please enter both username and password."

    username = username.strip().lower()
    if _memory.authenticate_user(username, password):
        return True, username, f"Welcome back, {username}!"
    return False, "", "Invalid username or password."
