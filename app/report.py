"""The report pipeline:

    transcript ──► safety rules (code) ──► Gemini triage ──► hospital search (our data + ratings)
               ──► Gemini report writer (must pick from our candidates) ──► facts added from data
                   (billing steps, directions, maps, inside-the-hospital steps)

    Animal questions (triage subject = "animal") branch after triage:
               ──► animal danger-sign rules (code) ──► vet search (our data) + district vet office + map search
               ──► Gemini vet guide writer (must pick from our candidate vets) ──► facts added from data

Facts that must be right (hospital list, distances, billing steps, map links) come from our data,
never from the model. The model only explains and chooses among real options.
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timedelta, timezone

from . import ai, hospitals, safety, vets
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


VET_URGENCY_TEXT = {
    "en": {"emergency": "Emergency: take it to a vet now", "urgent": "See a vet today",
           "soon": "See a vet within a few days", "routine": "Routine vet visit"},
    "ne": {"emergency": "आकस्मिक: अहिले नै पशु चिकित्सककहाँ लैजानुहोस्", "urgent": "आजै पशु चिकित्सकलाई देखाउनुहोस्",
           "soon": "केही दिनभित्र पशु चिकित्सकलाई देखाउनुहोस्", "routine": "सामान्य जाँच"},
}
VET_DISCLAIMER = {
    "en": "This guide helps you find care for your animal. It is not a vet's diagnosis. Never give human medicines "
          "to animals. Call the vet before you travel.",
    "ne": "यो निर्देशिकाले तपाईंको जनावरको उपचार कहाँ गर्ने भनेर मद्दत गर्छ। यो पशु चिकित्सकको जाँच होइन। जनावरलाई "
          "मान्छेको औषधि कहिल्यै नदिनुहोस्। जानुअघि पशु चिकित्सकलाई फोन गर्नुहोस्।",
}
ANIMAL_LABELS = {
    "rabbit": ("Rabbit", "खरायो"), "dog": ("Dog", "कुकुर"), "cat": ("Cat", "बिरालो"), "cow": ("Cow", "गाई"),
    "buffalo": ("Buffalo", "भैंसी"), "goat": ("Goat", "बाख्रा"), "sheep": ("Sheep", "भेडा"), "pig": ("Pig", "सुँगुर"),
    "chicken": ("Chicken", "कुखुरा"), "duck": ("Duck", "हाँस"), "bird": ("Bird", "चरा"),
    "guinea_pig": ("Guinea pig", "गिनी पिग"), "horse": ("Horse", "घोडा"), "fish": ("Fish", "माछा"),
}

NEPAL_TZ = timezone(timedelta(hours=5, minutes=45))


class NotHealthRelated(Exception):
    pass


def build_report(*, text: str, lang: str, lat: float | None = None, lng: float | None = None,
                 district: str | None = None) -> dict:
    t0 = time.time()
    check = safety.check_text(text)
    tri = ai.triage(text)
    # An animal bite on a person always stays a human case (rabies), whatever the model says.
    if tri.subject == "animal" and not safety.animal_bite(text):
        return build_vet_report(text=text, tri=tri, human_check=check, lang=lang, lat=lat, lng=lng,
                                district=district, t0=t0)
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


def _species_key(model_animal: str, text: str) -> str:
    key = (model_animal or "").strip().lower().replace(" ", "_")
    if key in ANIMAL_LABELS:
        return key
    return safety.animal_mentioned(text) or key


def build_vet_report(*, text: str, tri: ai.Triage, human_check: dict, lang: str, lat: float | None,
                     lng: float | None, district: str | None, t0: float) -> dict:
    species = _species_key(tri.animal, text)
    en, ne = ANIMAL_LABELS.get(species, ((tri.animal or "Animal").capitalize(), tri.animal or "जनावर"))
    animal_label = ne if lang == "ne" else en

    # Danger signs in code win over the model. Human red flags here describe the animal ("can't breathe"),
    # so they also mean "vet now".
    check = safety.check_animal(text)
    floor = "routine"
    if human_check["is_emergency"] or any(f["id"] != "animal_not_eating_small" for f in check["flags"]):
        floor = "emergency"
    elif check["flags"]:  # rabbit / guinea pig not eating: see a vet today
        floor = "urgent"
    urgency = max(tri.urgency, floor, key=["routine", "soon", "urgent", "emergency"].index)

    origin = hospitals.origin_from(lat, lng, district) or hospitals.origin_from(district=tri.district_mentioned)
    cands = vets.candidates(origin, species, lang)
    office = vets.district_office(origin, lang)
    search_url = vets.map_search_url("veterinary clinic", origin)
    origin_label = (origin or {}).get("label", "")
    out = ai.write_vet_report(text=text, animal=en, urgency=urgency, flags=check["flags"],
                              origin_label=origin_label if origin_label != "gps" else "GPS location",
                              office=(office or {}).get("name", ""), candidates=cands, lang=lang)

    pool = {c["id"]: c for c in cands}
    chosen, seen = [], set()
    for p in out.picks:
        if p.vet_id in pool and p.vet_id not in seen:
            chosen.append({**pool[p.vet_id], "why": p.why})
            seen.add(p.vet_id)
    if not chosen and cands:
        chosen = [{**cands[0], "why": ""}]

    return {
        "id": uuid.uuid4().hex[:12],
        "kind": "animal",
        "generated_at": datetime.now(NEPAL_TZ).strftime("%Y-%m-%d %H:%M"),
        "lang": lang,
        "transcript": text,
        "animal": species,
        "animal_label": animal_label,
        "urgency": urgency,
        "urgency_text": VET_URGENCY_TEXT[lang][urgency],
        "origin": origin,
        "safety_flags": [{"label": f[f"label_{lang}"], "action": f[f"action_{lang}"]} for f in check["flags"]],
        "title": out.title,
        "summary": out.summary,
        "urgency_reason": out.urgency_reason,
        "do_now": out.do_now,
        "care_at_home": out.care_at_home,
        "food_tips": out.food_tips,
        "hospitals": chosen[:3],  # the vets (same key as hospitals so PDF, email and share work unchanged)
        "district_office": office,
        "vet_search_url": search_url,
        "tell_the_vet": out.tell_the_vet,
        "warning_signs": out.warning_signs,
        "travel_tip": out.travel_tip,
        "disclaimer": VET_DISCLAIMER[lang],
        "seconds": round(time.time() - t0, 1),
    }

