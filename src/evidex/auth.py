"""Local accounts, salted scrypt passwords, hashed opaque sessions, and ownership."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

SESSION_SECONDS = 7 * 24 * 60 * 60


def password_hash(password: str, salt: bytes) -> str:
    return hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1).hex()


class AuthStore:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self.dummy_hash = password_hash("not-a-user-password", b"evidex-dummy-salt")
        with self.connection() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY, email TEXT NOT NULL UNIQUE,
                    salt TEXT NOT NULL, password_hash TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id),
                    expires REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS ownership (
                    job_id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id),
                    demo INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS rate_limits (
                    key TEXT PRIMARY KEY, started REAL NOT NULL, attempts INTEGER NOT NULL
                );
            """)

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def allow_attempt(self, key: str, limit: int = 10, window: int = 900) -> bool:
        key = hashlib.sha256(key.encode()).hexdigest()
        now = time.time()
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM rate_limits WHERE started < ?", (now - window,))
            row = db.execute("SELECT attempts FROM rate_limits WHERE key=?", (key,)).fetchone()
            if row and row[0] >= limit:
                return False
            db.execute(
                "INSERT INTO rate_limits VALUES (?, ?, 1) ON CONFLICT(key) "
                "DO UPDATE SET attempts=attempts+1",
                (key, now),
            )
        return True

    def register(self, email: str, password: str) -> dict:
        salt = secrets.token_bytes(16)
        uid = secrets.token_hex(16)
        encoded = password_hash(password, salt)
        with self.connection() as db:
            db.execute("INSERT INTO users VALUES (?, ?, ?, ?)", (uid, email, salt.hex(), encoded))
        return {"id": uid, "email": email}

    def login(self, email: str, password: str) -> dict | None:
        with self.connection() as db:
            row = db.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        salt = bytes.fromhex(row["salt"]) if row else b"evidex-dummy-salt"
        actual = password_hash(password, salt)
        expected = row["password_hash"] if row else self.dummy_hash
        valid = hmac.compare_digest(actual, expected)
        return {"id": row["id"], "email": row["email"]} if row and valid else None

    def session(self, user_id: str) -> str:
        token = secrets.token_urlsafe(32)
        with self.connection() as db:
            db.execute("DELETE FROM sessions WHERE expires < ?", (time.time(),))
            db.execute(
                "INSERT INTO sessions VALUES (?, ?, ?)",
                (
                    hashlib.sha256(token.encode()).hexdigest(),
                    user_id,
                    time.time() + SESSION_SECONDS,
                ),
            )
        return token

    def user(self, token: str) -> dict | None:
        with self.connection() as db:
            row = db.execute(
                "SELECT users.id, users.email FROM sessions JOIN users "
                "ON users.id=sessions.user_id WHERE token_hash=? AND expires>?",
                (hashlib.sha256(token.encode()).hexdigest(), time.time()),
            ).fetchone()
        return dict(row) if row else None

    def logout(self, token: str):
        with self.connection() as db:
            db.execute(
                "DELETE FROM sessions WHERE token_hash=?",
                (hashlib.sha256(token.encode()).hexdigest(),),
            )

    def assign(self, job_id: str, user_id: str, demo: bool):
        with self.connection() as db:
            db.execute("INSERT INTO ownership VALUES (?, ?, ?)", (job_id, user_id, demo))

    def projects(self, user_id: str) -> list[dict]:
        with self.connection() as db:
            return [
                dict(row)
                for row in db.execute(
                    "SELECT job_id, demo FROM ownership WHERE user_id=? ORDER BY rowid DESC",
                    (user_id,),
                )
            ]

    def owned(self, job_id: str, user_id: str) -> dict | None:
        with self.connection() as db:
            row = db.execute(
                "SELECT * FROM ownership WHERE job_id=? AND user_id=?", (job_id, user_id)
            ).fetchone()
        return dict(row) if row else None
