"""
إضافات أثر لخادم FastAPI (صدوف)
=================================
يضيف إلى الخادم:
  GET  /health             -> اللعبة توقظ به الخادم عند فتحها (Render المجاني ينام بعد 15 دقيقة)
  GET  /api/child-report   -> نتائج طفل واحد، تقرؤها صفحة الوالدين
  GET  /parents            -> صفحة الوالدين (parents.html في نفس المجلد)
ويحفظ أحداث /api/log-event في قاعدة بيانات.

طريقة الاستخدام (3 أسطر في main.py):
    from athar_parents import register, save_event
    register(app)                      # بعد إنشاء app = FastAPI(...)
    # داخل دالة /api/log-event الموجودة، قبل return:
    save_event(body.child_id, body.situation_id, body.classification, body.timestamp)

التخزين:
  - بدون إعداد: SQLite في ملف athar.db (ممتاز للتجربة، لكنه يُمسح في Render المجاني عند إعادة التشغيل أو النشر).
  - للحفظ الدائم: ضعي متغير البيئة DATABASE_URL (Postgres، مثل Render Postgres أو Neon)
    وأضيفي إلى requirements.txt السطر:  psycopg[binary]
"""
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Query
from fastapi.responses import FileResponse, JSONResponse

HERE = Path(__file__).resolve().parent
PARENTS_HTML = HERE / "parents.html"
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
SQLITE_PATH = os.getenv("ATHAR_SQLITE", str(HERE / "athar.db"))

VALID_RESULTS = {"excellent", "neutral", "poor"}


def _connect():
    """يرجع (اتصال، رمز المتغير في SQL)."""
    if DATABASE_URL:
        import psycopg  # pip install "psycopg[binary]"
        return psycopg.connect(DATABASE_URL), "%s"
    return sqlite3.connect(SQLITE_PATH), "?"


def init_db() -> None:
    con, _ = _connect()
    try:
        id_col = "id SERIAL PRIMARY KEY" if DATABASE_URL else "id INTEGER PRIMARY KEY AUTOINCREMENT"
        con.execute(f"""
            CREATE TABLE IF NOT EXISTS athar_events (
                {id_col},
                child_id       TEXT NOT NULL,
                situation_id   TEXT,
                classification TEXT NOT NULL,
                ts             TEXT NOT NULL,
                hadith_text    TEXT,
                hadith_source  TEXT
            )""")
        con.execute("CREATE INDEX IF NOT EXISTS ix_athar_events_child ON athar_events (child_id)")
        con.commit()
    finally:
        con.close()


def _clip(value: Optional[str], n: int) -> Optional[str]:
    if value is None:
        return None
    value = str(value).strip()
    return value[:n] if value else None


def save_event(child_id: str, situation_id: Optional[str], classification: str,
               timestamp: Optional[str] = None,
               hadith_text: Optional[str] = None, hadith_source: Optional[str] = None) -> bool:
    """يحفظ نتيجة مرحلة. لا يرمي أخطاء حتى لا يتعطل /api/log-event."""
    try:
        child_id = _clip(child_id, 64)
        classification = (classification or "").strip().lower()
        if not child_id or classification not in VALID_RESULTS:
            return False
        ts = _clip(timestamp, 40) or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        con, ph = _connect()
        try:
            con.execute(
                f"INSERT INTO athar_events (child_id, situation_id, classification, ts, hadith_text, hadith_source) "
                f"VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph})",
                (child_id, _clip(situation_id, 64), classification, ts,
                 _clip(hadith_text, 2000), _clip(hadith_source, 300)))
            con.commit()
        finally:
            con.close()
        return True
    except Exception as e:  # noqa: BLE001
        print("athar save_event error:", e)
        return False


def child_report(child_id: str = Query(..., min_length=3, max_length=64)):
    con, ph = _connect()
    try:
        cur = con.execute(
            f"SELECT situation_id, classification, ts, hadith_text, hadith_source "
            f"FROM athar_events WHERE child_id = {ph} ORDER BY id DESC LIMIT 200",
            (child_id.strip(),))
        rows = cur.fetchall()
    finally:
        con.close()
    events = [
        {"situation_id": r[0], "classification": r[1], "timestamp": r[2],
         "hadith_text": r[3], "hadith_source": r[4]}
        for r in rows
    ]
    return JSONResponse({"child_id": child_id, "events": events},
                        headers={"Cache-Control": "no-store"})


def health():
    return {"ok": True}


def parents_page():
    return FileResponse(PARENTS_HTML, media_type="text/html; charset=utf-8")


def register(app: FastAPI) -> None:
    init_db()
    app.add_api_route("/health", health, methods=["GET"])
    app.add_api_route("/api/child-report", child_report, methods=["GET"])
    app.add_api_route("/parents", parents_page, methods=["GET"], include_in_schema=False)
