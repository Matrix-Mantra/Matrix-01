"""Vet directory and the links that always work: the district government vet office and a live map search.

Every district has a government Veterinary Hospital and Livestock Service Expert Centre. Named clinics come
from vets.json (OpenStreetMap import + manual checks). When none is close, the report still gives the
district office and a Google Maps search for vets near the person, which shows live, real results.
"""

from __future__ import annotations

import json
from functools import lru_cache
from urllib.parse import quote, urlencode

from . import config, hospitals

MAX_KM = 60

TYPE_LABELS = {
    "government": ("Government vet hospital", "सरकारी पशु अस्पताल"),
    "teaching": ("Veterinary teaching hospital", "पशु चिकित्सा शिक्षण अस्पताल"),
    "private": ("Private vet clinic", "निजी पशु क्लिनिक"),
    "ngo": ("Animal welfare / NGO clinic", "पशु कल्याण / गैरसरकारी क्लिनिक"),
}
DISTRICT_OFFICE = {
    "en": "Veterinary Hospital and Livestock Service Expert Centre, {district}",
    "ne": "पशु अस्पताल तथा पशु सेवा विज्ञ केन्द्र, {district}",
}


@lru_cache(maxsize=1)
def all_vets() -> list[dict]:
    with open(config.DATA_DIR / "vets.json", encoding="utf-8") as f:
        return json.load(f)["vets"]


def type_label(t: str, lang: str) -> str:
    en, ne = TYPE_LABELS.get(t, TYPE_LABELS["private"])
    return ne if lang == "ne" else en


def map_search_url(query: str, origin: dict | None) -> str:
    """Google Maps search, centred on the person when we know where they are."""
    if origin:
        return f"https://www.google.com/maps/search/{quote(query)}/@{origin['lat']},{origin['lng']},13z"
    return "https://www.google.com/maps/search/?" + urlencode({"api": 1, "query": query + " Nepal"})


def nearest_district(origin: dict | None) -> str | None:
    if not origin:
        return None
    if origin.get("label") and origin["label"] != "gps":
        return origin["label"]
    dmap, _ = hospitals.districts()
    return min(dmap, key=lambda d: hospitals.haversine_km(origin["lat"], origin["lng"], *dmap[d]))


def district_office(origin: dict | None, lang: str) -> dict | None:
    district = nearest_district(origin)
    if not district:
        return None
    return {
        "name": DISTRICT_OFFICE[lang].format(district=district),
        "search_url": map_search_url(f"Veterinary Hospital and Livestock Service Expert Centre {district}", origin),
    }


def candidates(origin: dict | None, species: str, lang: str, n: int = 4) -> list[dict]:
    """Nearest vets within MAX_KM that treat this kind of animal."""
    if not origin:
        return []
    livestock = species in ("cow", "buffalo", "goat", "sheep", "pig", "chicken", "duck", "horse")
    rows = []
    for v in all_vets():
        if v.get("animals") == "pets" and livestock or v.get("animals") == "livestock" and not livestock:
            continue
        km = hospitals.haversine_km(origin["lat"], origin["lng"], v["lat"], v["lng"])
        if km <= MAX_KM:
            rows.append({
                "id": v["id"], "name": v["name"], "name_ne": v.get("name_ne"), "city": v.get("city"),
                "district": v.get("district"), "type_label": type_label(v.get("type", "private"), lang),
                "phone": v.get("phone") or "", "verified": bool(v.get("verified")), "distance_km": round(km, 1),
                "directions_url": hospitals.directions_url(v, origin),
                "map_embed_url": hospitals.map_embed_url(v, origin),
            })
    rows.sort(key=lambda r: r["distance_km"])
    return rows[:n]
