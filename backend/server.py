from datetime import datetime
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

try:
    from app.kb import HADITH
except Exception:
    HADITH = []


app = FastAPI(title="Athar Backend", version="0.1.0")

# Unity can call the API from any origin during the prototype.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class NextScenarioRequest(BaseModel):
    child_id: str
    situation_id: str
    child_age: int
    language: str = "ar"


class LogEventRequest(BaseModel):
    child_id: str
    situation_id: str
    classification: str
    timestamp: Optional[str] = None


def choose_hadith(situation_id: str, language: str):
    wanted = "أمانة" if situation_id == "amanah" else "صدق" if situation_id == "sidq" else None

    candidates = [
        h for h in HADITH
        if wanted is None or h.get("value") == wanted
    ]

    if not candidates and HADITH:
        candidates = HADITH

    if not candidates:
        return {
            "text": "لم تتم إضافة حديث معتمد إلى قاعدة المعرفة بعد.",
            "source": "Athar fallback",
        }

    h = candidates[0]
    text_key = "text_en" if language.lower().startswith("en") else "text_ar"
    return {
        "text": h.get(text_key) or h.get("text_ar") or "",
        "source": f'{h.get("book", "")} — حديث {h.get("hadith_number", "")}',
    }


@app.get("/")
def health():
    return {"ok": True, "service": "athar-backend", "status": "running"}


@app.get("/health")
def health_check():
    return {"ok": True}


@app.post("/api/next-scenario")
def next_scenario(request: NextScenarioRequest):
    hadith = choose_hadith(request.situation_id, request.language)

    # Static fallback for the first Unity integration.
    if request.situation_id == "amanah":
        lines = [
            "أحسنت، خلّينا نفكر في الأمانة معًا.",
            "الأمانة تعني أن نحفظ ما اؤتمنّا عليه ونؤدي حقّه.",
        ]
    elif request.situation_id == "sidq":
        lines = [
            "خلّينا نفكر في الصدق معًا.",
            "قول الحقيقة يساعدنا على فعل الصواب.",
        ]
    else:
        lines = [
            "خلّينا نفكر في الموقف معًا.",
            "اختر التصرف الذي يرضي الله ويحفظ حق الآخرين.",
        ]

    return {
        "lines": lines,
        "hadith_text": hadith["text"],
        "hadith_source": hadith["source"],
    }


@app.post("/api/log-event")
def log_event(request: LogEventRequest):
    # Prototype only: acknowledge the event.
    # Persistent storage can be added later.
    return {"ok": True}
