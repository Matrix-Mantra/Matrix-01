"""Hospital directory: data loading, search, distance, billing and wayfinding info."""

from __future__ import annotations

import difflib
import json
import math
from functools import lru_cache
from urllib.parse import urlencode

from . import config

TYPE_LABELS = {
    "government": ("Government hospital", "सरकारी अस्पताल"),
    "government_teaching": ("Government teaching hospital", "सरकारी शिक्षण अस्पताल"),
    "government_specialty": ("Government specialty centre", "सरकारी विशेषज्ञ केन्द्र"),
    "nonprofit": ("Community / non-profit hospital", "सामुदायिक / गैरनाफामूलक अस्पताल"),
    "nonprofit_teaching": ("Non-profit teaching hospital", "गैरनाफामूलक शिक्षण अस्पताल"),
    "nonprofit_specialty": ("Non-profit specialty centre", "गैरनाफामूलक विशेषज्ञ केन्द्र"),
    "private": ("Private hospital", "निजी अस्पताल"),
    "private_teaching": ("Private teaching hospital", "निजी शिक्षण अस्पताल"),
    "unknown": ("Hospital", "अस्पताल"),
}

FAR_KM = 80


def _load(name: str) -> dict:
    with open(config.DATA_DIR / name, encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=1)
def all_hospitals() -> list[dict]:
    return _load("hospitals.json")["hospitals"]


@lru_cache(maxsize=1)
def by_id() -> dict[str, dict]:
    return {h["id"]: h for h in all_hospitals()}


@lru_cache(maxsize=1)
def departments() -> dict:
    return _load("departments.json")


@lru_cache(maxsize=1)
def billing_data() -> dict:
    return _load("billing.json")


@lru_cache(maxsize=1)
def districts() -> tuple[dict, dict]:
    d = _load("districts.json")
    return d["districts"], d["aliases"]


@lru_cache(maxsize=1)
def schemes() -> list[dict]:
    return _load("schemes.json")["schemes"]


def dept_label(dept: str, lang: str) -> str:
    d = departments().get(dept)
    return d[lang] if d else dept


def type_label(t: str, lang: str) -> str:
    en, ne = TYPE_LABELS.get(t, TYPE_LABELS["unknown"])
    return ne if lang == "ne" else en


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def resolve_district(name: str | None) -> str | None:
    """District or city name (English, romanized or Devanagari) -> canonical district."""
    if not name:
        return None
    dmap, aliases = districts()
    key = name.strip()
    low = key.lower()
    for d in dmap:
        if d.lower() == low:
            return d
    if low in aliases:
        return aliases[low]
    if key in aliases:
        return aliases[key]
    m = difflib.get_close_matches(low, [d.lower() for d in dmap] + list(aliases), n=1, cutoff=0.8)
    if m:
        return aliases.get(m[0]) or next(d for d in dmap if d.lower() == m[0])
    return None


def origin_from(lat: float | None = None, lng: float | None = None, district: str | None = None) -> dict | None:
    if lat is not None and lng is not None:
        return {"lat": lat, "lng": lng, "label": "gps"}
    d = resolve_district(district)
    if d:
        lat, lng = districts()[0][d]
        return {"lat": lat, "lng": lng, "label": d}
    return None


def normalize_department(dept: str | None) -> str | None:
    if not dept:
        return None
    d = dept.strip().lower().replace(" ", "_").replace("-", "_")
    if d in departments():
        return d
    m = difflib.get_close_matches(d, list(departments()), n=1, cutoff=0.7)
    return m[0] if m else None


# ------------------------------------------------------------------ links


def directions_url(h: dict, origin: dict | None = None) -> str:
    params = {"api": "1", "destination": f"{h['lat']},{h['lng']}", "travelmode": "driving"}
    if origin:
        params["origin"] = f"{origin['lat']},{origin['lng']}"
    return "https://www.google.com/maps/dir/?" + urlencode(params)


def google_maps_place_url(h: dict) -> str:
    """Opens the hospital in Google Maps, where people can also read Google reviews."""
    return "https://www.google.com/maps/search/?" + urlencode({"api": "1", "query": f"{h['name']}, {h['city']}, Nepal"})


def map_embed_url(h: dict, origin: dict | None = None, satellite: bool = False) -> str:
    """Iframe URL. With a Maps Embed API key and an origin, shows a route; otherwise a pin on the hospital."""
    if config.MAPS_EMBED_API_KEY and origin and not satellite:
        q = urlencode({"key": config.MAPS_EMBED_API_KEY, "origin": f"{origin['lat']},{origin['lng']}",
                       "destination": f"{h['lat']},{h['lng']}", "mode": "driving"})
        return f"https://www.google.com/maps/embed/v1/directions?{q}"
    if config.MAPS_EMBED_API_KEY:
        q = urlencode({"key": config.MAPS_EMBED_API_KEY, "q": f"{h['lat']},{h['lng']}", "zoom": 17 if satellite else 15,
                       "maptype": "satellite" if satellite else "roadmap"})
        return f"https://www.google.com/maps/embed/v1/place?{q}"
    return f"https://maps.google.com/maps?q={h['lat']},{h['lng']}&z={17 if satellite else 15}&t={'k' if satellite else 'm'}&output=embed"


# ------------------------------------------------------------------ billing / wayfinding


def billing_group(h: dict) -> str:
    t = h.get("type", "")
    if t.startswith("government"):
        return "government"
    if t.startswith("private"):
        return "private"
    return "nonprofit"


def billing_info(h: dict, lang: str, emergency: bool = False) -> dict:
    b = billing_data()
    return {
        "group": billing_group(h),
        "steps": b["emergency"][lang] if emergency else b["opd"][billing_group(h)][lang],
        "insurance_steps": b["insurance"][lang] if h.get("health_insurance") else [],
        "help": b["help"][lang],
        "hospital_notes": h.get("billing_notes"),
        "general_guidance": True,
    }


def inside_steps(h: dict, dept: str | None, lang: str) -> dict:
    """How to reach the department inside the hospital. Hospital-specific text if we have it."""
    specific = (h.get("wayfinding") or {}).get(dept or "")
    label = dept_label(dept, lang) if dept else ("the right" if lang == "en" else "सम्बन्धित")
    generic = [s.replace("{department}", label) for s in billing_data()["inside"][lang]]
    return {"specific": specific, "steps": generic, "campus_map_url": h.get("campus_map_url"),
            "satellite_embed_url": map_embed_url(h, satellite=True)}


# ------------------------------------------------------------------ search


def public_view(h: dict, lang: str = "ne", origin: dict | None = None) -> dict:
    row = {
        "id": h["id"], "name": h["name"], "name_ne": h.get("name_ne"), "type": h.get("type", "unknown"),
        "type_label": type_label(h.get("type", "unknown"), lang), "city": h.get("city"), "district": h.get("district"),
        "province": h.get("province"), "lat": h["lat"], "lng": h["lng"], "emergency_24h": h.get("emergency_24h"),
        "health_insurance": h.get("health_insurance"), "departments": h.get("departments", []),
        "phone": h.get("phone"), "website": h.get("website"), "verified": h.get("verified", False),
        "directions_url": directions_url(h, origin), "google_maps_url": google_maps_place_url(h),
    }
    if origin:
        row["distance_km"] = round(haversine_km(origin["lat"], origin["lng"], h["lat"], h["lng"]), 1)
    return row


def _matches(h: dict, q: str) -> bool:
    if not q:
        return True
    q = q.strip().lower()
    hay = " ".join(str(h.get(k) or "") for k in ("name", "name_ne", "city", "district", "province")).lower()
    if q in hay:
        return True
    d = resolve_district(q)
    return bool(d and d == h.get("district"))


def search(q: str = "", district: str | None = None, department: str | None = None, origin: dict | None = None,
           emergency_only: bool = False, lang: str = "ne", limit: int | None = None) -> list[dict]:
    dept = normalize_department(department) if department else None
    dist = resolve_district(district) if district else None
    rows = []
    for h in all_hospitals():
        if dist and h.get("district") != dist:
            continue
        if dept and dept not in h.get("departments", []):
            continue
        if emergency_only and not h.get("emergency_24h"):
            continue
        if not _matches(h, q):
            continue
        rows.append(public_view(h, lang, origin))
    if origin:
        rows.sort(key=lambda r: r["distance_km"])
    else:
        rows.sort(key=lambda r: (r["province"] or "", r["district"] or "", r["name"]))
    return rows[:limit] if limit else rows


def candidates(department: str, origin: dict | None, emergency: bool, lang: str, n: int = 5) -> dict:
    """Hospitals the report writer may choose from: right department, nearest first."""
    dept = normalize_department(department) or "general_medicine"
    rows = search(department=dept, origin=origin, emergency_only=emergency, lang=lang, limit=n)
    if not rows and emergency:
        rows = search(department=dept, origin=origin, lang=lang, limit=n)
    nearest_general = None
    if origin and rows and rows[0]["distance_km"] > FAR_KM and dept not in ("general_medicine", "emergency"):
        g = search(department="general_medicine", origin=origin, lang=lang, limit=1)
        if g and g[0]["distance_km"] < rows[0]["distance_km"]:
            nearest_general = g[0]
    return {"department": dept, "hospitals": rows, "nearest_general": nearest_general}


def find_schemes(text: str, lang: str) -> list[dict]:
    t = (text or "").lower()
    out = []
    for s in schemes():
        if s["id"] == "health_insurance":
            continue  # covered by billing info
        if any(k in t for k in s["keywords"]):
            out.append({"id": s["id"], "name": s[f"name_{lang}"], "summary": s[f"summary_{lang}"],
                        "how": s[f"how_to_use_{lang}"]})
    return out
