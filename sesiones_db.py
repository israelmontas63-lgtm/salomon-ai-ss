"""
Persistencia de sesiones de chat en SQLite.
Sobrevive reinicios del servidor.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "data" / "sesiones.db"


def _conexion() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def inicializar() -> None:
    with _conexion() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS sesiones (
                id TEXT PRIMARY KEY,
                creada_en TEXT NOT NULL,
                actualizada_en TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS mensajes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                rol TEXT NOT NULL,
                contenido TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES sesiones(id)
            );
            CREATE INDEX IF NOT EXISTS idx_mensajes_session
                ON mensajes(session_id, id);
        """)


def sesion_existe(session_id: str) -> bool:
    with _conexion() as conn:
        row = conn.execute(
            "SELECT 1 FROM sesiones WHERE id = ?",
            (session_id,),
        ).fetchone()
    return row is not None


def asegurar_sesion(session_id: str) -> None:
    ahora = datetime.now(timezone.utc).isoformat()
    with _conexion() as conn:
        conn.execute(
            """
            INSERT INTO sesiones (id, creada_en, actualizada_en)
            VALUES (?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET actualizada_en = excluded.actualizada_en
            """,
            (session_id, ahora, ahora),
        )


def guardar_mensaje(session_id: str, rol: str, contenido: str) -> None:
    if rol not in ("usuario", "asistente"):
        return

    ahora = datetime.now(timezone.utc).isoformat()
    asegurar_sesion(session_id)
    with _conexion() as conn:
        conn.execute(
            """
            INSERT INTO mensajes (session_id, rol, contenido, timestamp)
            VALUES (?, ?, ?, ?)
            """,
            (session_id, rol, contenido, ahora),
        )
        conn.execute(
            "UPDATE sesiones SET actualizada_en = ? WHERE id = ?",
            (ahora, session_id),
        )


def cargar_mensajes(session_id: str) -> list[dict[str, str]]:
    with _conexion() as conn:
        rows = conn.execute(
            """
            SELECT rol, contenido FROM mensajes
            WHERE session_id = ?
            ORDER BY id ASC
            """,
            (session_id,),
        ).fetchall()
    return [{"rol": row["rol"], "contenido": row["contenido"]} for row in rows]


def limpiar_sesion(session_id: str) -> None:
    with _conexion() as conn:
        conn.execute("DELETE FROM mensajes WHERE session_id = ?", (session_id,))
        conn.execute(
            "UPDATE sesiones SET actualizada_en = ? WHERE id = ?",
            (datetime.now(timezone.utc).isoformat(), session_id),
        )
