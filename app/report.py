"""The report pipeline:

    transcript ──► safety rules (code) ──► Gemini triage ──► hospital search (our data + ratings)
               ──► Gemini report writer (must pick from our candidates) ──► facts added from data
                   (billing steps, directions, maps, inside-the-hospital steps)

Facts that must be right (hospital list, distances, billing steps, map links) come from our data,
never from the model. The model only explains and chooses among real options.
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timedelta, timezone

from . import ai, hospitals, safety
from .store import get_store

URGENCY_TEXT = {
    "en": {"emergency": "Emergency: go now", "urgent": "See a doctor today", "soon": "See a doctor within a few days",
           "routine": "Normal OPD visit"},
    "ne": {"emergency": "आकस्मिक: अहिले नै जानुहोस्", "urgent": "आजै डाक्टरलाई देखाउनुहोस्",
           "soon": "केही दिनभित्र डाक्टरलाई देखाउनुहोस्", "routine": "सामान्य ओपीडी भेट"},
}
DISCLAIMER = {
    "en": "This guide helps you find the right hospital. It is not a medical diagnosis. Hospital details may change: "
          "call before you travel. In an emergency, call 102.",
    "ne": "यो निर्देशिकाले सही अस्पताल खोज्न मद्दत गर्छ। यो डाक्टरको जाँच वा रोग निदान होइन। अस्पतालको विवरण "
          "परिवर्तन हुन सक्छ: जानुअघि फोन गर्नुहोस्। आकस्मिक अवस्थामा १०२ मा फोन गर्नुहोस्।",
}


NEPAL_TZ = timezone(timedelta(hours=5, minutes=45))


class NotHealthRelated(Exception):
    pass


def build_report(*, text: str, lang: str, lat: float | None = None, lng: float | None = None,
                 district: str | None = None) -> dict:
    t0 = time.time()
    check = safety.check_text(text)
    tri = ai.triage(text)
    if not tri.is_health_problem and not check["is_emergency"]:
        raise NotHealthRelated()

    urgency, department = tri.urgency, hospitals.normalize_department(tri.department) or "general_medicine"
    if check["is_emergency"]:  # the code-level safety layer always wins
        urgency, department = "emergency", "emergency"
    is_emergency = urgency == "emergency"

    origin = hospitals.origin_from(lat, lng, district) or hospitals.origin_from(district=tri.district_mentioned)
    cand = hospitals.candidates(department, origin, emergency=is_emergency, lang=lang)
    ratings = get_store().summaries()
    for h in cand["hospitals"] + ([cand["nearest_general"]] if cand["nearest_general"] else []):
        h["rating"] = ratings.get(h["id"])

    dlabel = hospitals.dept_label(department, lang)
    origin_label = (origin or {}).get("label", "")
    text_out = ai.write_report(text=text, triage_result=tri, department=department, department_label=dlabel,
                               origin_label=origin_label if origin_label != "gps" else "GPS location",
                               candidates=cand["hospitals"], nearest_general=cand["nearest_general"], lang=lang)

    # Keep only hospitals that really are candidates; fall back to the nearest if the model picked none.
    pool = {h["id"]: h for h in cand["hospitals"]}
    if cand["nearest_general"]:
        pool.setdefault(cand["nearest_general"]["id"], cand["nearest_general"])
    picks, seen = [], set()
    for p in text_out.picks:
        if p.hospital_id in pool and p.hospital_id not in seen:
            picks.append((pool[p.hospital_id], p.why))
            seen.add(p.hospital_id)
    if not picks and cand["hospitals"]:
        picks = [(cand["hospitals"][0], "")]
    picks = picks[:3]

    chosen = []
    for h, why in picks:
        raw = hospitals.by_id()[h["id"]]
        dept_here = department if department in raw.get("departments", []) else "general_medicine"
        chosen.append({
            **h,
            "why": why,
            "map_embed_url": hospitals.map_embed_url(raw, origin),
            "directions_url": hospitals.directions_url(raw, origin),
            "billing": hospitals.billing_info(raw, lang, emergency=is_emergency),
            "inside": hospitals.inside_steps(raw, dept_here, lang),
        })

    dept_info = hospitals.departments()[department]
    return {
        "id": uuid.uuid4().hex[:12],
        "generated_at": datetime.now(NEPAL_TZ).strftime("%Y-%m-%d %H:%M"),
        "lang": lang,
        "transcript": text,
        "urgency": urgency,
        "urgency_text": URGENCY_TEXT[lang][urgency],
        "department": department,
        "department_label": dlabel,
        "department_about": dept_info[f"about_{lang}"],
        "alternative_department": hospitals.normalize_department(tri.alternative_department) if not is_emergency else None,
        "origin": origin,
        "safety_flags": [{"label": f[f"label_{lang}"], "action": f[f"action_{lang}"]} for f in check["flags"]],
        "title": text_out.title,
        "summary": text_out.summary,
        "urgency_reason": text_out.urgency_reason,
        "do_now": text_out.do_now,
        "department_reason": text_out.department_reason,
        "hospitals": chosen,
        "what_to_bring": text_out.what_to_bring,
        "questions_for_doctor": text_out.questions_for_doctor,
        "warning_signs": text_out.warning_signs,
        "travel_tip": text_out.travel_tip,
        "schemes": hospitals.find_schemes(text + " " + " ".join(tri.key_symptoms) + (" poor" if tri.cost_worry else ""), lang),
        "disclaimer": DISCLAIMER[lang],
        "seconds": round(time.time() - t0, 1),
    }
