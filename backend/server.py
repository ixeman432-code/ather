from typing import Optional
import json
import os
import random
import re

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.kb import get_hadith_pool  


app = FastAPI(title="Athar Backend", version="0.1.0")

# Parent report routes + event storage.
from athar_parents import register, save_event

register(app)


# Unity can call the API from any origin during the prototype.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class NextScenarioRequest(BaseModel):
    # Original fields remain supported.
    # Defaults prevent errors if a field is missing.
    child_id: str = ""
    situation_id: str = "amanah"
    child_age: int = 8
    language: str = "ar"

    # New scenario fields.
    classification: Optional[str] = None
    child_gender: str = "male"
    bird_came: Optional[bool] = None
    bird_pecked: Optional[bool] = None
    left_area: Optional[bool] = None
    away_seconds: Optional[int] = None
    duration_seconds: Optional[int] = None


class LogEventRequest(BaseModel):
    child_id: str = ""
    situation_id: str = "amanah"
    classification: str = "neutral"
    timestamp: Optional[str] = None

    # Unity can pass the exact hadith returned by /next-scenario.
    hadith_text: Optional[str] = None
    hadith_source: Optional[str] = None


VALID_CLASSIFICATIONS = {"excellent", "neutral", "poor"}
VALID_GENDERS = {"male", "female"}
VALID_LANGUAGES = {"ar", "en"}

# Prevent accidental AI output from containing a hadith.
FORBIDDEN_HADITH_PHRASES = (
    "قال رسول",
    "رسول الله",
    "النبي",
    "حديث",
    "صلى الله",
    "ﷺ",
    "the prophet",
    "prophet muhammad",
    "hadith",
)

# Same child should not receive the same hadith twice consecutively.
# This is intentionally in-memory for the prototype.
last_hadith = {}


def normalize_classification(value: Optional[str]) -> str:
    value = (value or "").strip().lower()
    return value if value in VALID_CLASSIFICATIONS else "neutral"


def normalize_gender(value: Optional[str]) -> str:
    value = (value or "").strip().lower()
    return value if value in VALID_GENDERS else "male"


def normalize_language(value: Optional[str]) -> str:
    value = (value or "").strip().lower()
    return value if value in VALID_LANGUAGES else "ar"


def choose_hadith(
    child_id: str,
    classification: str,
    language: str,
    child_age: int,
):
    """
    Select an approved hadith directly from the current Excel-derived KB.

    The KB handles:
      excellent -> ثناء
      neutral   -> تشجيع
      poor      -> تنبيه لطيف

    Age mapping is handled by app.kb:
      4-9  -> workbook target 9
      10-12 -> workbook target 10

    Claude is never used to write, translate, summarize, or choose the hadith.
    """
    language = normalize_language(language)
    pool = get_hadith_pool(classification, child_age, language)

    if not pool:
        return {"text": "", "source": "", "id": ""}

    previous = last_hadith.get(child_id)

    # Avoid the same text twice consecutively when another choice exists.
    if len(pool) > 1 and previous:
        alternatives = [
            h for h in pool
            if h.get("text", "") != previous
        ]
        if alternatives:
            pool = alternatives

    h = random.choice(pool)

    if language == "en":
        # The current workbook has no approved English translations.
        # get_hadith_pool already filters out blank English text.
        text = h.get("text_en", "")
    else:
        text = h.get("text", "")

    source = h.get("source", "")

    # Never expose the word "fallback" in hadith_source.
    if "fallback" in source.lower():
        source = ""

    if text:
        last_hadith[child_id] = h.get("text", "")

    return {
        "text": text,
        "source": source,
        "id": h.get("id", ""),
    }


def _fallback_lines(
    classification: str,
    language: str,
    gender: str,
):
    language = normalize_language(language)
    gender = normalize_gender(gender)

    if language == "en":
        if classification == "excellent":
            return [
                "Well done!",
                "You stayed close and kept the trust safe. Thank you for being responsible.",
            ]
        if classification == "poor":
            return [
                "Oh, the bird reached the basket and ate the pastries, so our picnic was spoiled.",
                "It is okay to learn from what happened and try to keep the trust safe next time.",
            ]
        return [
            "You did well by staying nearby and keeping an eye on the trust.",
            "Thank you for trying to keep it safe.",
        ]

    if gender == "female":
        if classification == "excellent":
            return [
                "أحسنتِ يا بطلة!",
                "بقيتِ قريبة وحافظتِ على الأمانة، شكرًا لكِ على تصرفكِ المسؤول.",
            ]
        if classification == "poor":
            return [
                "يا للأسف، وصل الطائر إلى السلة وأكل المعجنات، وفسدت نزهتنا.",
                "لا بأس، نتعلم مما حدث ونحاول أن نحافظ على الأمانة في المرة القادمة.",
            ]
        return [
            "أحسنتِ على بقائكِ قريبة ومتابعتكِ للأمانة.",
            "الحمد لله أن الطائر لم يصل إلى السلة، وحاولي دائمًا أن تحافظي عليها.",
        ]

    if classification == "excellent":
        return [
            "أحسنتَ يا بطل!",
            "بقيتَ قريبًا وحافظتَ على الأمانة، شكرًا لكَ على تصرفكَ المسؤول.",
        ]
    if classification == "poor":
        return [
            "يا للأسف، وصل الطائر إلى السلة وأكل المعجنات، وفسدت نزهتنا.",
            "لا بأس، نتعلم مما حدث ونحاول أن نحافظ على الأمانة في المرة القادمة.",
        ]
    return [
        "أحسنتَ على بقائك قريبًا ومتابعتك للأمانة.",
        "الحمد لله أن الطائر لم يصل إلى السلة، وحاول دائمًا أن تحافظ عليها.",
    ]


def _contains_hadith(text: str) -> bool:
    lowered = (text or "").lower()
    return any(phrase.lower() in lowered for phrase in FORBIDDEN_HADITH_PHRASES)


def _clean_ai_lines(raw) -> list[str]:
    if isinstance(raw, dict):
        raw = raw.get("lines") or raw.get("dialogue") or []

    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                raw = parsed.get("lines") or parsed.get("dialogue") or raw
            elif isinstance(parsed, list):
                raw = parsed
        except Exception:
            pass

    if isinstance(raw, str):
        parts = re.split(r"(?<=[.!؟])\s+|\n+", raw)
    elif isinstance(raw, list):
        parts = [str(item) for item in raw]
    else:
        return []

    cleaned = []
    for part in parts:
        part = re.sub(r"^\s*[-•*\d.)]+\s*", "", part).strip()
        if not part or _contains_hadith(part):
            continue
        if part not in cleaned:
            cleaned.append(part)

    return cleaned[:3]


def generate_ai_lines(
    classification: str,
    language: str,
    gender: str,
    child_age: int,
) -> list[str]:
    """
    Claude writes only Rashad's dialogue.
    Hadith text/source are never sent to Claude for rewriting or translation.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        return []

    try:
        import anthropic

        model = os.getenv("CLAUDE_MODEL", "claude-haiku-4-5-20251001")

        client = anthropic.Anthropic(
            api_key=api_key,
            timeout=2.3,
            max_retries=0,
        )

        if language == "en":
            scenario = {
                "excellent": (
                    "The child stayed near the basket and the bird did not approach. "
                    "Rashad returns, welcomes the child, and thanks them for keeping the trust."
                ),
                "neutral": (
                    "The child moved away a little. A bird approached the area but did not reach "
                    "the basket. Rashad praises staying nearby, says the bird did not eat, and "
                    "encourages keeping the trust."
                ),
                "poor": (
                    "The child moved too far away or for too long. The bird reached the basket, "
                    "ate the pastries, and the picnic was spoiled. Rashad should express gentle "
                    "sadness without fear, shouting, or scolding, then encourage learning from it."
                ),
            }[classification]

            system = (
                "You are Uncle Rashad, a kind grandfather-like village elder speaking to a child. "
                "Write exactly 2 short, simple English sentences as ordinary dialogue. "
                "Use natural gender-neutral English. Do not translate, quote, summarize, or mention any hadith. ""Do not mention the Prophet, religious quotations, punishment, fear, or AI. "
                "Do not scold. Return JSON only: "
                '{"lines":["sentence 1","sentence 2"]}'
            )
        else:
            scenario = {
                "excellent": (
                    "بقي الطفل قريبًا من السلة ولم يقترب الطائر. عاد العم رشاد ورحّب بالطفل "
                    "وشكره لأنه حافظ على الأمانة."
                ),
                "neutral": (
                    "ابتعد الطفل قليلًا، واقترب طائر من المكان لكنه لم يصل إلى السلة. "
                    "يمدح العم رشاد بقاء الطفل قريبًا ويقول الحمد لله أن الطائر لم يأكل، "
                    "ويشجعه على المحافظة على الأمانة."
                ),
                "poor": (
                    "ابتعد الطفل كثيرًا أو لمدة طويلة، فوصل الطائر إلى السلة وأكل المعجنات "
                    "وفسدت النزهة. يعبّر العم رشاد عن حزن لطيف بلا تخويف أو توبيخ، "
                    "ثم يشجع الطفل على التعلم مما حدث."
                ),
            }[classification]

            # IMPORTANT: gender rule is first.
            if gender == "female":
                gender_rule = (
                    "المخاطَبة بنت. استخدم صيغة المؤنث في كل جملة بدون استثناء: "
                    "أنتِ، أحسنتِ، تعالي، رجعتِ، حافظتِ، يا بطلة. ممنوع أي صيغة مذكر."
                )
            else:
                gender_rule = (
                    "المخاطَب ولد. استخدم صيغة المذكر: "
                    "أنتَ، أحسنتَ، تعال، رجعتَ، حافظتَ، يا بطل."
                )

            system = (
                f"{gender_rule}\n"
                "أنت العم رشاد، رجل كبير لطيف يتحدث مع الطفل مثل الجد الحنون. "
                "اكتب جملتين قصيرتين وبسيطتين جدًا يفهمهما طفل. "
                "لا تذكر أي حديث أو آية أو نص ديني، ولا تكتب اسم النبي، "
                "ولا تستخدم التخويف أو العقاب أو التوبيخ، ولا تقل إنك ذكاء اصطناعي. "
                "أعد JSON فقط بهذا الشكل: "
                '{"lines":["الجملة الأولى","الجملة الثانية"]}'
            )

        gender_text = "female" if gender == "female" else "male"

        response = client.messages.create(
            model=model,
            max_tokens=180,
            system=system,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Child age: {max(int(child_age or 0), 1)}. "
                        f"Child gender: {gender_text}. "
                        f"Classification: {classification}. "
                        f"Scenario: {scenario}"
                    ),
                }
            ],
        )

        raw_text = ""
        for block in getattr(response, "content", []) or []:
            if getattr(block, "type", "") == "text":
                raw_text += getattr(block, "text", "")

        return _clean_ai_lines(raw_text)

    except Exception:
        return []


@app.get("/")
def root():
    return {"ok": True, "service": "athar-backend", "status": "running"}


@app.get("/health")
def health_check():
    return {"ok": True}


@app.post("/api/next-scenario")
def next_scenario(request: NextScenarioRequest):
    classification = normalize_classification(request.classification)
    language = normalize_language(request.language)
    gender = normalize_gender(request.child_gender)

    hadith = choose_hadith(
        request.child_id,
        classification,
        language,
        request.child_age,
    )

    lines = generate_ai_lines(
        classification,
        language,
        gender,
        request.child_age,
    )

    if len(lines) < 2:
        lines = _fallback_lines(classification, language, gender)

    return {
        "lines": lines[:3],
        "hadith_text": hadith["text"],
        "hadith_source": hadith["source"],
    }


@app.post("/api/log-event")
def log_event(request: LogEventRequest):
    save_event(
        request.child_id,
        request.situation_id,
        request.classification,
        request.timestamp,
        request.hadith_text,
        request.hadith_source,
    )
    return {"ok": True}
