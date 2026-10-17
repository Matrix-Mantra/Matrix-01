"""Gemini calls: Nepali speech recognition, triage, and report writing.

All model outputs that the app relies on are requested as JSON with a schema, so the code never
has to guess what the model meant.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import tempfile
import time
from functools import lru_cache
from pathlib import Path
from typing import Literal

from google import genai
from google.genai import errors, types
from pydantic import BaseModel, Field

from . import config

log = logging.getLogger(__name__)

Urgency = Literal["emergency", "urgent", "soon", "routine"]
Department = Literal["emergency", "general_medicine", "general_surgery", "cardiology", "neurology", "neurosurgery",
                     "orthopedics", "obstetrics_gynecology", "pediatrics", "ophthalmology", "ent", "dermatology",
                     "psychiatry", "oncology", "nephrology", "gastroenterology", "pulmonology", "urology", "dental",
                     "burns"]


@lru_cache(maxsize=1)
def client() -> genai.Client:
    return genai.Client()


# Busy (503), rate-limited (429) or retired (404) models: try the next one instead of failing the request.
_RETRY_CODES = {404, 429, 500, 503}


def _generate(model: str, fallbacks: list[str] | None = None, **kwargs):
    fallbacks = config.FALLBACK_MODELS if fallbacks is None else fallbacks
    models = [model] + [m for m in fallbacks if m != model]
    attempts = [(r, m) for r in range(2) for m in models]  # two rounds: demand spikes are usually short
    for i, (round_no, name) in enumerate(attempts):
        if round_no and name == models[0]:
            time.sleep(2)
        try:
            return client().models.generate_content(model=name, **kwargs)
        except errors.APIError as exc:
            if exc.code not in _RETRY_CODES or i == len(attempts) - 1:
                raise
            log.warning("Gemini model %s failed (%s), trying %s", name, exc.code, attempts[i + 1][1])


def is_busy(exc: BaseException) -> bool:
    """True when Gemini failed because it is overloaded or rate-limited, not because of the input."""
    return isinstance(exc, errors.APIError) and exc.code in (429, 503)


def _json_call(model: str, contents: list, schema: type[BaseModel], temperature: float = 0.2) -> BaseModel:
    resp = _generate(
        model,
        contents=contents,
        config=types.GenerateContentConfig(temperature=temperature, response_mime_type="application/json",
                                           response_schema=schema),
    )
    if getattr(resp, "parsed", None) is not None:
        return resp.parsed
    return schema.model_validate(json.loads(resp.text))


# ------------------------------------------------------------------ speech


GEMINI_AUDIO = {"audio/wav", "audio/x-wav", "audio/mp3", "audio/mpeg", "audio/aiff", "audio/aac", "audio/ogg", "audio/flac"}


def _ffmpeg_path() -> str:
    """System ffmpeg (Docker image), else the binary bundled with imageio-ffmpeg (local development)."""
    if path := shutil.which("ffmpeg"):
        return path
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("ffmpeg is not installed") from exc


def to_supported_audio(data: bytes, mime_type: str) -> tuple[bytes, str]:
    """Browsers record webm/mp4; convert to 16 kHz mono WAV with ffmpeg."""
    base = (mime_type or "").split(";")[0].strip().lower()
    if base in GEMINI_AUDIO:
        return data, base
    ffmpeg = _ffmpeg_path()
    with tempfile.TemporaryDirectory() as tmp:
        src, dst = Path(tmp) / "in", Path(tmp) / "out.wav"
        src.write_bytes(data)
        subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-i", str(src), "-ac", "1", "-ar", "16000", str(dst)],
                       check=True, timeout=60)
        return dst.read_bytes(), "audio/wav"


TRANSCRIBE_PROMPT = """\
Transcribe this voice recording exactly as spoken. The speaker is most likely speaking Nepali, possibly
mixed with English, Maithili, Bhojpuri, Tharu or Newari words. Write Nepali in Devanagari script.
Do not translate, summarise, correct or add anything. Return only the transcript.
If there is no clear speech, return an empty string."""


def transcribe(data: bytes, mime_type: str) -> str:
    audio, mime = to_supported_audio(data, mime_type)
    resp = _generate(
        config.SPEECH_MODEL,
        contents=[types.Part.from_bytes(data=audio, mime_type=mime), TRANSCRIBE_PROMPT],
        config=types.GenerateContentConfig(temperature=0.0),
    )
    return (resp.text or "").strip()


# ------------------------------------------------------------------ read aloud (text → speech)


def _pcm_to_wav(pcm: bytes, rate: int = 24000) -> bytes:
    import io
    import wave

    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    return buf.getvalue()


def _to_mp3(wav: bytes) -> tuple[bytes, str]:
    """Smaller download for phones; WAV if ffmpeg is missing or fails."""
    try:
        ffmpeg = _ffmpeg_path()
        with tempfile.TemporaryDirectory() as tmp:
            src, dst = Path(tmp) / "in.wav", Path(tmp) / "out.mp3"
            src.write_bytes(wav)
            subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-i", str(src), "-ac", "1", "-b:a", "64k", str(dst)],
                           check=True, timeout=60)
            return dst.read_bytes(), "audio/mpeg"
    except Exception:  # noqa: BLE001
        log.warning("mp3 conversion failed, sending wav")
        return wav, "audio/wav"


def speak(text: str) -> tuple[bytes, str]:
    """Natural speech for `text` (Nepali or English). Only the text is sent: any instruction would be read aloud."""
    resp = _generate(
        config.TTS_MODEL, config.TTS_FALLBACK_MODELS, contents=text,
        config=types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=config.TTS_VOICE)))),
    )
    part = resp.candidates[0].content.parts[0].inline_data
    data = part.data if part.data[:4] == b"RIFF" else _pcm_to_wav(part.data)  # some models send raw 24 kHz PCM
    return _to_mp3(data)


# ------------------------------------------------------------------ step 1: triage


class Triage(BaseModel):
    is_health_problem: bool = Field(description="False if the text does not describe a health problem or need "
                                                "(of a person or of an animal).")
    subject: Literal["person", "animal"] = Field(description="'animal' if the problem is about a pet or farm animal; "
                                                             "'person' if about a human, including a person bitten "
                                                             "or scratched by an animal.")
    animal: str = Field(description="If subject is animal: the kind of animal in English, e.g. 'rabbit', 'cow'. "
                                    "Otherwise empty.")
    patient: str = Field(description="Who is sick and their age if mentioned, e.g. 'father, 62'. Empty if unknown.")
    key_symptoms: list[str] = Field(description="Main symptoms in short words, in the transcript's language.")
    duration: str = Field(description="How long it has been happening, if mentioned. Empty if unknown.")
    urgency: Urgency
    department: Department = Field(description="The single best hospital department to visit first.")
    alternative_department: str = Field(description="A second suitable department from the same list, or empty.")
    district_mentioned: str = Field(description="Nepal district or city the speaker says they are in, in English. Empty if none.")
    cost_worry: bool = Field(description="True if the speaker worries about money or mentions being poor.")


TRIAGE_PROMPT = """\
You help people in Nepal find the right hospital department. You are NOT a doctor and must not diagnose.
Read what the person said (it may be Nepali, romanized Nepali or English, and may contain speech-recognition
mistakes) and fill in the fields.

People also ask about their animals (pets like rabbits, dogs, cats, birds; farm animals like cows, buffaloes,
goats, chickens). Then set subject="animal", name the animal, and judge urgency FOR THE ANIMAL with the same
levels. A rabbit or guinea pig that has stopped eating is at least "urgent". If an animal bit or scratched a
PERSON, the subject is "person" (rabies risk: urgency at least "urgent", department "emergency" or
"general_medicine"). For animals, set department to "general_medicine" (it is not used).

Urgency rules:
- emergency: danger signs now (chest pain, severe breathing trouble, unconscious, fits, stroke signs, heavy
  bleeding, pregnancy bleeding or severe pain, snake bite, poisoning, serious injury or burn, suicidal thoughts,
  a baby who is not feeding or is very weak). department must then be "emergency".
- urgent: should see a doctor today (e.g. high fever for 3+ days, severe pain, child with fever and not eating).
- soon: within a few days. routine: a normal OPD visit is fine.
When unsure between two levels, choose the more urgent one.
Department: choose where a patient in Nepal would normally go FIRST. Use general_medicine for unclear adult
problems and pediatrics for children under 15.

What the person said:
\"\"\"{text}\"\"\""""


def triage(text: str) -> Triage:
    return _json_call(config.TRIAGE_MODEL, [TRIAGE_PROMPT.format(text=text)], Triage, temperature=0.1)


# ------------------------------------------------------------------ step 2: report


class Pick(BaseModel):
    hospital_id: str = Field(description="Must be one of the candidate ids.")
    why: str = Field(description="One short sentence: why this hospital (distance, department, insurance, ratings).")


class ReportText(BaseModel):
    title: str = Field(description="Short title, e.g. 'Chest pain: go to the emergency department now'.")
    summary: str = Field(description="2-3 simple sentences: what the person told us and what we suggest.")
    urgency_reason: str = Field(description="One sentence on why this level of urgency.")
    do_now: list[str] = Field(description="2-4 short, practical steps to take now, most important first.")
    department_reason: str = Field(description="One sentence: why this department, in plain words.")
    picks: list[Pick] = Field(description="1-3 hospitals from the candidates, best first.")
    what_to_bring: list[str] = Field(description="3-6 things to bring (ID, insurance card, old reports, medicines...).")
    questions_for_doctor: list[str] = Field(description="2-4 simple questions to ask the doctor.")
    warning_signs: list[str] = Field(description="2-4 signs that mean go to emergency immediately.")
    travel_tip: str = Field(description="One practical tip about getting there or timing. Empty if nothing useful.")


REPORT_PROMPT = """\
You write a short, clear hospital visit guide for a person in Nepal who may have little education.
Write ALL text in {language}. Use simple everyday words and short sentences. Explain any medical word you use.

STRICT RULES
- You are not a doctor. Do not diagnose or name a disease the person might have. Do not suggest medicines or doses.
- Choose hospitals ONLY from the candidate list, by id. Do not invent hospitals, phone numbers, prices, doctors
  or opening hours. Prefer closer hospitals; for a non-emergency also consider government hospitals and health
  insurance acceptance; use ratings only as a tie-breaker.
- If urgency is emergency, the first do_now step must be to call 102 for an ambulance or go to the nearest
  emergency department right now.
- If a nearest_general hospital is given and the problem is not an emergency, mention in do_now or travel_tip
  that they can be examined there first and get a referral.

What the person said: \"\"\"{text}\"\"\"
Triage: {triage}
Department to visit: {department} ({department_label})
Person's location: {origin}
Candidate hospitals (JSON): {candidates}
Nearest general hospital (JSON, may be null): {nearest_general}"""


class VetPick(BaseModel):
    vet_id: str = Field(description="Must be one of the candidate vet ids.")
    why: str = Field(description="One short sentence: why this place (distance, type).")


class VetReportText(BaseModel):
    title: str = Field(description="Short title, e.g. 'Rabbit not eating: see a vet today'.")
    summary: str = Field(description="2-3 simple sentences: what the person told us and what we suggest.")
    urgency_reason: str = Field(description="One sentence on why this level of urgency for the animal.")
    do_now: list[str] = Field(description="2-4 short, practical steps to take now, most important first.")
    care_at_home: list[str] = Field(description="2-5 safe general comfort steps until the vet visit (warmth, quiet, "
                                                "water). No medicines.")
    food_tips: list[str] = Field(description="2-4 tips on what this animal normally eats and what to offer now. "
                                             "Empty if feeding is not relevant.")
    picks: list[VetPick] = Field(description="0-3 vets from the candidates, best first. Empty if there are none.")
    tell_the_vet: list[str] = Field(description="2-4 things to tell or ask the vet (when it started, what it ate...).")
    warning_signs: list[str] = Field(description="2-4 signs that mean go to a vet immediately.")
    travel_tip: str = Field(description="One practical tip about taking the animal there. Empty if nothing useful.")


VET_PROMPT = """\
You write a short, clear guide for a person in Nepal whose animal is unwell. They may have little education.
Write ALL text in {language}. Use simple everyday words and short sentences.

STRICT RULES
- You are not a vet. Do not diagnose or name a disease. You may say what kind of problem it could be in plain,
  general words only if it helps the person act (e.g. "its stomach may have stopped working"), never as a certainty.
- Never suggest any medicine or dose, and tell the person NOT to give human medicines (many are poisonous to animals).
- Choose vets ONLY from the candidate list, by id. Do not invent clinics, phone numbers, prices or opening hours.
  If the candidate list is empty, leave picks empty: the app adds the district government vet office and a map
  search for vets nearby.
- If urgency is emergency, the first do_now step must be to take the animal to a vet right now.
- Food tips must be standard, safe feeding for this kind of animal (e.g. rabbits: plenty of hay, fresh greens,
  water; no bread, sweets or cooked food).

What the person said: \"\"\"{text}\"\"\"
Animal: {animal}
Urgency for the animal: {urgency}
Danger signs found by our rules (JSON): {flags}
Person's location: {origin}
District government vet office: {office}
Candidate vets (JSON, may be empty): {candidates}"""


def write_vet_report(*, text: str, animal: str, urgency: str, flags: list[dict], origin_label: str,
                     office: str, candidates: list[dict], lang: str) -> VetReportText:
    slim = [{k: c.get(k) for k in ("id", "name", "type_label", "city", "district", "distance_km")} for c in candidates]
    prompt = VET_PROMPT.format(
        language="simple Nepali (Devanagari script)" if lang == "ne" else "simple English", text=text,
        animal=animal or "unknown", urgency=urgency, flags=json.dumps([f["label_en"] for f in flags]),
        origin=origin_label or "unknown", office=office or "unknown",
        candidates=json.dumps(slim, ensure_ascii=False),
    )
    return _json_call(config.REPORT_MODEL, [prompt], VetReportText, temperature=0.3)


class ReportTranslation(BaseModel):
    """The parts of a report the model wrote. Facts from our data are rebuilt in the new language instead."""
    title: str = ""
    summary: str = ""
    urgency_reason: str = ""
    do_now: list[str] = Field(default_factory=list)
    department_reason: str = ""
    what_to_bring: list[str] = Field(default_factory=list)
    questions_for_doctor: list[str] = Field(default_factory=list)
    warning_signs: list[str] = Field(default_factory=list)
    travel_tip: str = ""
    care_at_home: list[str] = Field(default_factory=list)
    food_tips: list[str] = Field(default_factory=list)
    tell_the_vet: list[str] = Field(default_factory=list)
    hospital_whys: list[str] = Field(default_factory=list, description="One per hospital, same order.")


TRANSLATE_PROMPT = """\
Translate every text value in this JSON into {language}. It is a hospital or vet visit guide for a person in
Nepal who may have little education: use simple everyday words and short sentences.
Keep exactly the same keys, the same number of items in every list, and the same order. Keep numbers, names
of hospitals and places, and phone numbers as they are. Do not add, remove or change any advice.
Empty values stay empty.

JSON:
{payload}"""


def translate_report(texts: dict, lang: str) -> ReportTranslation:
    prompt = TRANSLATE_PROMPT.format(
        language="simple Nepali (Devanagari script)" if lang == "ne" else "simple English",
        payload=json.dumps(texts, ensure_ascii=False))
    return _json_call(config.REPORT_MODEL, [prompt], ReportTranslation, temperature=0.1)


def write_report(*, text: str, triage_result: Triage, department: str, department_label: str, origin_label: str,
                 candidates: list[dict], nearest_general: dict | None, lang: str) -> ReportText:
    slim = lambda h: None if h is None else {  # noqa: E731
        k: h.get(k) for k in ("id", "name", "type_label", "city", "district", "distance_km", "emergency_24h",
                              "health_insurance", "rating")
    }
    prompt = REPORT_PROMPT.format(
        language="simple Nepali (Devanagari script)" if lang == "ne" else "simple English",
        text=text, triage=triage_result.model_dump_json(), department=department, department_label=department_label,
        origin=origin_label or "unknown", candidates=json.dumps([slim(c) for c in candidates], ensure_ascii=False),
        nearest_general=json.dumps(slim(nearest_general), ensure_ascii=False),
    )
    return _json_call(config.REPORT_MODEL, [prompt], ReportText, temperature=0.3)
