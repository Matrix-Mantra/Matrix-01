"""FastAPI app: the web page and the JSON API."""

from __future__ import annotations

import logging
import os
from typing import Literal

from fastapi import Depends, FastAPI, File, HTTPException, Query, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from . import ai, config, hospitals, pdf, report, safety
from .auth import User, check_limit, current_user
from .store import get_store

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
log = logging.getLogger("swasthya")

app = FastAPI(title="Matrix", version="2.0.0")
app.mount("/static", StaticFiles(directory=config.STATIC_DIR), name="static")


@app.middleware("http")
async def security_headers(request, call_next):
    resp = await call_next(request)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    resp.headers.setdefault("Permissions-Policy", "microphone=(self), geolocation=(self), camera=()")
    return resp


# ------------------------------------------------------------------ pages and config


@app.get("/")
def index() -> FileResponse:
    return FileResponse(config.STATIC_DIR / "index.html")


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "hospitals": len(hospitals.all_hospitals()), "auth": config.AUTH_MODE, "store": config.STORE}


@app.get("/api/config")
def app_config() -> dict:
    """Everything the browser needs at start-up (all of it is public information)."""
    dmap, _ = hospitals.districts()
    return {
        "auth_mode": config.AUTH_MODE,
        "firebase": config.FIREBASE_WEB_CONFIG if config.AUTH_MODE == "firebase" else None,
        "districts": sorted(dmap),
        "departments": hospitals.departments(),
        "osm_attribution": any(h.get("source") == "osm" for h in hospitals.all_hospitals()),
    }


@app.get("/api/me")
def me(user: User = Depends(current_user)) -> dict:
    return {"uid": user.uid, "name": user.name}


# ------------------------------------------------------------------ hospitals and reviews (public read)


@app.get("/api/hospitals")
def list_hospitals(
    q: str = Query("", max_length=80),
    district: str | None = Query(None, max_length=60),
    department: str | None = Query(None, max_length=40),
    lat: float | None = Query(None, ge=26, le=31),
    lng: float | None = Query(None, ge=79.5, le=88.5),
    near: str | None = Query(None, max_length=60, description="District to sort by distance from"),
    lang: Literal["ne", "en"] = "ne",
) -> dict:
    origin = hospitals.origin_from(lat, lng) if lat is not None and lng is not None else hospitals.origin_from(district=near)
    rows = hospitals.search(q=q, district=district, department=department, origin=origin, lang=lang)
    ratings = get_store().summaries()
    for r in rows:
        r["rating"] = ratings.get(r["id"])
        r.pop("departments", None)  # keep the list light
    return {"count": len(rows), "hospitals": rows}


def _hospital_or_404(hospital_id: str) -> dict:
    h = hospitals.by_id().get(hospital_id)
    if not h:
        raise HTTPException(404, "Hospital not found.")
    return h


@app.get("/api/hospitals/{hospital_id}")
def hospital_detail(hospital_id: str, lang: Literal["ne", "en"] = "ne",
                    lat: float | None = Query(None, ge=26, le=31), lng: float | None = Query(None, ge=79.5, le=88.5)) -> dict:
    h = _hospital_or_404(hospital_id)
    origin = hospitals.origin_from(lat, lng) if lat is not None and lng is not None else None
    view = hospitals.public_view(h, lang, origin)
    view["department_labels"] = [{"id": d, "label": hospitals.dept_label(d, lang)} for d in h.get("departments", [])]
    view["map_embed_url"] = hospitals.map_embed_url(h)
    view["billing"] = hospitals.billing_info(h, lang)
    view["inside"] = hospitals.inside_steps(h, None, lang)
    view["rating"] = get_store().summaries().get(hospital_id)
    view["reviews"] = get_store().list_reviews(hospital_id)
    for rv in view["reviews"]:
        rv.pop("uid", None)
    return view


class ReviewIn(BaseModel):
    rating: int = Field(ge=1, le=5)
    comment: str = Field(default="", max_length=config.MAX_COMMENT_CHARS)


@app.get("/api/hospitals/{hospital_id}/my-review")
def my_review(hospital_id: str, user: User = Depends(current_user)) -> dict:
    _hospital_or_404(hospital_id)
    for rv in get_store().list_reviews(hospital_id, limit=500):
        if rv["uid"] == user.uid:
            rv.pop("uid")
            return {"review": rv}
    return {"review": None}


@app.post("/api/hospitals/{hospital_id}/reviews")
def post_review(hospital_id: str, body: ReviewIn, user: User = Depends(current_user)) -> dict:
    _hospital_or_404(hospital_id)
    check_limit(user, "review", 50)
    comment = " ".join(body.comment.split())  # collapse whitespace
    saved = get_store().upsert_review(hospital_id, user.uid, user.name, body.rating, comment)
    saved.pop("uid", None)
    return {"review": saved, "rating": get_store().summaries().get(hospital_id)}


@app.delete("/api/hospitals/{hospital_id}/reviews/mine")
def delete_review(hospital_id: str, user: User = Depends(current_user)) -> dict:
    _hospital_or_404(hospital_id)
    return {"deleted": get_store().delete_review(hospital_id, user.uid)}


# ------------------------------------------------------------------ voice → report (login required)


async def _read_upload(upload: UploadFile) -> bytes:
    data = await upload.read(config.MAX_UPLOAD_BYTES + 1)
    if len(data) > config.MAX_UPLOAD_BYTES:
        raise HTTPException(413, "Recording is too long. Please keep it under 2 minutes.")
    if len(data) < 500:
        raise HTTPException(400, "Recording is empty. Please try again.")
    return data


@app.post("/api/transcribe")
async def transcribe(audio: UploadFile = File(...), user: User = Depends(current_user)) -> dict:
    check_limit(user, "transcribe", config.DAILY_TRANSCRIBE_LIMIT)
    data = await _read_upload(audio)
    try:
        text = ai.transcribe(data, audio.content_type or "audio/webm")
    except Exception as exc:
        log.exception("transcription failed")
        if ai.is_busy(exc):
            raise HTTPException(503, "The voice service is busy right now. Please try again in a minute, or type instead.") from exc
        raise HTTPException(502, "Could not understand the recording. Please try again or type instead.") from exc
    return {"text": text, "safety": safety.check_text(text)}


class ReportRequest(BaseModel):
    text: str = Field(min_length=3, max_length=config.MAX_TRANSCRIPT_CHARS)
    lang: Literal["ne", "en"] = "ne"
    lat: float | None = Field(default=None, ge=26, le=31)
    lng: float | None = Field(default=None, ge=79.5, le=88.5)
    district: str | None = Field(default=None, max_length=60)


@app.post("/api/report")
def make_report(req: ReportRequest, user: User = Depends(current_user)):
    check_limit(user, "report", config.DAILY_REPORT_LIMIT)
    check = safety.check_text(req.text)
    try:
        return report.build_report(text=req.text, lang=req.lang, lat=req.lat, lng=req.lng, district=req.district)
    except report.NotHealthRelated:
        raise HTTPException(422, "We could not find a health problem in what you said. Please describe the problem again.")
    except Exception:
        log.exception("report failed")
        # Even if the AI is down, never hide an emergency.
        return JSONResponse(status_code=502, content={
            "detail": "The report service is not reachable right now. Please try again.",
            "safety": check,
        })


# ------------------------------------------------------------------ PDF


class _Loose(BaseModel):
    model_config = ConfigDict(extra="allow")


class PdfHospital(_Loose):
    id: str = Field(max_length=80)
    name: str = Field(max_length=200)
    directions_url: str = Field(max_length=500, pattern=r"^https://www\.google\.com/maps/")


class PdfReport(_Loose):
    lang: Literal["ne", "en"]
    urgency: Literal["emergency", "urgent", "soon", "routine"]
    title: str = Field(max_length=300)
    summary: str = Field(max_length=2000)
    transcript: str = Field(max_length=config.MAX_TRANSCRIPT_CHARS)
    hospitals: list[PdfHospital] = Field(max_length=3)


@app.post("/api/report/pdf")
def report_pdf(body: PdfReport, user: User = Depends(current_user)) -> Response:
    check_limit(user, "pdf", 100)
    try:
        data = pdf.render_pdf(body.model_dump())
    except Exception as exc:
        log.exception("pdf failed")
        raise HTTPException(400, "Could not create the PDF from this report.") from exc
    return Response(content=data, media_type="application/pdf",
                    headers={"Content-Disposition": 'attachment; filename="hospital-guide.pdf"'})
