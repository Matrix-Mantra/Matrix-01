"""Add every hospital in Nepal from OpenStreetMap to app/data/hospitals.json.

Run on your own computer (needs internet):

    python -m scripts.import_osm            # fetch from the Overpass API and merge
    python -m scripts.import_osm --dry-run  # just show what would be added

What it does
- Downloads all OSM objects tagged amenity=hospital inside Nepal.
- Skips any that match a hospital we already have (same name, or within 300 m).
- Adds the rest with departments=[] ("not yet listed"), verified=false and source="osm".
  The directory shows them; the report only recommends hospitals whose departments are known,
  so fill in departments for the important ones first.

OpenStreetMap data is © OpenStreetMap contributors, ODbL. Keep the attribution in the app footer/README.
"""

from __future__ import annotations

import argparse
import json
import re
import urllib.parse
import urllib.request
from pathlib import Path

from app import hospitals as H

DATA = Path(__file__).resolve().parent.parent / "app" / "data" / "hospitals.json"
OVERPASS = "https://overpass-api.de/api/interpreter"
QUERY = """
[out:json][timeout:120];
area["ISO3166-1"="NP"][admin_level=2]->.np;
(
  node["amenity"="hospital"](area.np);
  way["amenity"="hospital"](area.np);
  relation["amenity"="hospital"](area.np);
);
out center tags;
"""


def fetch() -> dict:
    data = urllib.parse.urlencode({"data": QUERY}).encode()
    req = urllib.request.Request(OVERPASS, data=data, headers={"User-Agent": "swasthya-saathi-importer/1.0"})
    with urllib.request.urlopen(req, timeout=180) as resp:
        return json.load(resp)


def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9ऀ-ॿ]+", "", (name or "").lower())


def _type_from_tags(tags: dict) -> str:
    op = (tags.get("operator:type") or tags.get("healthcare:type") or "").lower()
    if op in ("government", "public"):
        return "government"
    if op in ("private", "commercial"):
        return "private"
    if op in ("community", "ngo", "non_profit", "religious", "charitable"):
        return "nonprofit"
    return "unknown"


def nearest_district(lat: float, lng: float) -> str:
    dmap, _ = H.districts()
    return min(dmap, key=lambda d: H.haversine_km(lat, lng, dmap[d][0], dmap[d][1]))


def convert(osm: dict, existing: list[dict]) -> list[dict]:
    known_names = {_norm(h["name"]) for h in existing} | {_norm(h.get("name_ne") or "") for h in existing}
    known_names.discard("")
    added: list[dict] = []
    for el in osm.get("elements", []):
        tags = el.get("tags", {})
        name = tags.get("name:en") or tags.get("name")
        if not name:
            continue
        lat = el.get("lat") or (el.get("center") or {}).get("lat")
        lng = el.get("lon") or (el.get("center") or {}).get("lon")
        if lat is None or lng is None:
            continue
        if _norm(name) in known_names or _norm(tags.get("name:ne", "")) in known_names:
            continue
        if any(H.haversine_km(lat, lng, h["lat"], h["lng"]) < 0.3 for h in existing + added):
            continue
        district = nearest_district(lat, lng)
        added.append({
            "id": f"osm-{el['type'][0]}{el['id']}",
            "name": name.strip(),
            "name_ne": (tags.get("name:ne") or "").strip() or None,
            "type": _type_from_tags(tags),
            "city": tags.get("addr:city") or tags.get("addr:place") or district,
            "district": district,
            "province": None,
            "lat": round(lat, 5), "lng": round(lng, 5),
            "emergency_24h": True if tags.get("emergency") == "yes" else None,
            "health_insurance": None,
            "departments": [],
            "phone": tags.get("phone") or tags.get("contact:phone"),
            "website": tags.get("website") or tags.get("contact:website"),
            "wayfinding": {}, "campus_map_url": None, "billing_notes": None,
            "source": "osm", "source_url": f"https://www.openstreetmap.org/{el['type']}/{el['id']}",
            "verified": False,
        })
        known_names.add(_norm(name))
    return added


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--from-file", help="use a saved Overpass JSON response instead of downloading")
    args = ap.parse_args()
    data = json.loads(DATA.read_text(encoding="utf-8"))
    osm = json.loads(Path(args.from_file).read_text(encoding="utf-8")) if args.from_file else fetch()
    new = convert(osm, data["hospitals"])
    print(f"OSM hospitals found: {len(osm.get('elements', []))}; new to add: {len(new)}")
    for h in new[:15]:
        print(f"  + {h['name']} ({h['district']})")
    if args.dry_run:
        return
    data["hospitals"].extend(new)
    DATA.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"Saved. Total hospitals: {len(data['hospitals'])}")


if __name__ == "__main__":
    main()
