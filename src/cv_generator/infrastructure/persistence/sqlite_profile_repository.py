from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from cv_generator.domain.models import MasterProfile, utc_now_iso


class SQLiteProfileRepository:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS profiles (
                    profile_id TEXT PRIMARY KEY,
                    data_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS profile_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    profile_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload_json TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def get(self, profile_id: str) -> MasterProfile | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT data_json FROM profiles WHERE profile_id = ?",
                (profile_id,),
            ).fetchone()
        if row is None:
            return None
        return MasterProfile.from_dict(json.loads(row["data_json"]))

    def save(
        self,
        profile: MasterProfile,
        event_type: str = "upsert",
        payload: dict[str, Any] | None = None,
    ) -> None:
        profile.metadata.setdefault("created_at", utc_now_iso())
        profile.metadata["updated_at"] = utc_now_iso()
        data_json = json.dumps(profile.to_dict(), ensure_ascii=False, indent=2)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO profiles (profile_id, data_json, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(profile_id) DO UPDATE SET
                  data_json=excluded.data_json,
                  updated_at=excluded.updated_at
                """,
                (profile.profile_id, data_json, profile.metadata["updated_at"]),
            )
            conn.execute(
                """
                INSERT INTO profile_events (profile_id, event_type, payload_json, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    profile.profile_id,
                    event_type,
                    json.dumps(payload or {}, ensure_ascii=False),
                    utc_now_iso(),
                ),
            )
            conn.commit()

    def export_json(self, profile_id: str, output_path: Path) -> Path:
        profile = self.get(profile_id)
        if profile is None:
            raise KeyError(f"Perfil no encontrado: {profile_id}")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(profile.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        return output_path
