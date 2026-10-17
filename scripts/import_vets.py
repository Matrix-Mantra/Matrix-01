"""Add every vet clinic and animal hospital in Nepal from OpenStreetMap to app/data/vets.json.

Run on your own computer (needs internet):

    python -m scripts.import_vets            # fetch from the Overpass API and merge
    python -m scripts.import_vets --dry-run  # just show what would be added

What it does
- Downloads all OSM objects tagged amenity=veterinary or healthcare=veterinary inside Nepal.
- Skips any that match a vet we already have (same name, or within 200 m).
- Adds the rest with verified=false and source="osm". Check the ones in the areas you demo, then set
  verified: true (and "animals": "pets" or "livestock" if the clinic only treats one kind).

OpenStreetMap data is © OpenStreetMap contributors, ODbL. Keep the attribution in the app footer/README.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app import hospitals as H
from scripts.import_osm import _norm, nearest_district

DATA = Path(__file__).resolve().parent.parent / "app" / "data" / "vets.json"
MIRRORS = ("https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter",
           "https://overpass.private.coffee/api/interpreter")
QUERY = """
[out:json][timeout:120];
area["ISO3166-1"="NP"][admin_level=2]->.np;
(
  nwr["amenity"="veterinary"](area.np);
  nwr["healthcare"="veterinary"](area.np);
);
out center tags;
"""


def fetch() -> dict:
    import urllib.parse
    import urllib.request

    data = urllib.parse.urlencode({"data": QUERY}).encode()
    try:  # python.org builds on macOS ship without root certificates; certifi has them
        import ssl

        import certifi

        ctx = ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        ctx = None
    last: Exception | None = None
    for url in MIRRORS:  # the public servers are often busy; try each
        try:
            req = urllib.request.Request(url, data=data, headers={"User-Agent": "matrix-vet-importer/1.0"})
            with urllib.request.urlopen(req, timeout=180, context=ctx) as resp:
                return json.load(resp)
        except Exception as exc:  # noqa: BLE001
            print(f"  {url} failed: {exc}")
            last = exc
    raise SystemExit(f"All Overpass servers failed ({last}). Try again later.")


def _type_from_tags(tags: dict) -> str:
    op = (tags.get("operator:type") or "").lower()
    if op in ("government", "public"):
        return "government"
    if op in ("ngo", "non_profit", "charitable", "community"):
        return "ngo"
    if "university" in (tags.get("operator") or "").lower() or "teaching" in (tags.get("name") or "").lower():
        return "teaching"
    return "private"


# Agrovets are mostly shops (medicine, feed), not clinics; generic or private names are not usable places.
SKIP_WORDS = ("agro", "residen", "house", "home", "store", "shop", "farm", "pharma", "suppl", "feed", "traders",
              "pasal", "पसल", "mart", "aausadi", "औषधि")
GENERIC = {"veterinary", "veterinaryclinic", "vetclinic", "vet", "veterinaryhospital", "pashuaspatal",
           "veterinarydoctor", "पशुचिकित्सक", "पशुअस्पताल"}


def usable(name: str) -> bool:
    low = name.lower()
    return _norm(name) not in GENERIC and not any(w in low for w in SKIP_WORDS)


def convert(osm: dict, existing: list[dict]) -> list[dict]:
    known = {_norm(v["name"]) for v in existing} | {_norm(v.get("name_ne") or "") for v in existing}
    known.discard("")
    added: list[dict] = []
    for el in osm.get("elements", []):
        tags = el.get("tags", {})
        name = tags.get("name:en") or tags.get("name")
        lat = el.get("lat") or (el.get("center") or {}).get("lat")
        lng = el.get("lon") or (el.get("center") or {}).get("lon")
        if not name or lat is None or lng is None or _norm(name) in known or not usable(name):
            continue
        if any(H.haversine_km(lat, lng, v["lat"], v["lng"]) < 0.2 for v in existing + added):
            continue
        district = nearest_district(lat, lng)
        added.append({
            "id": f"osm-{el['type'][0]}{el['id']}",
            "name": name.strip(),
            "name_ne": (tags.get("name:ne") or "").strip() or None,
            "city": tags.get("addr:city") or tags.get("addr:place") or district,
            "district": district,
            "province": None,
            "lat": round(lat, 5), "lng": round(lng, 5),
            "phone": tags.get("phone") or tags.get("contact:phone") or "",
            "type": _type_from_tags(tags),
            "animals": "all",
            "verified": False,
            "source": "osm",
            "source_url": f"https://www.openstreetmap.org/{el['type']}/{el['id']}",
        })
        known.add(_norm(name))
    return added


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--from-file", help="use a saved Overpass JSON response instead of downloading")
    args = ap.parse_args()
    data = json.loads(DATA.read_text(encoding="utf-8"))
    osm = json.loads(Path(args.from_file).read_text(encoding="utf-8")) if args.from_file else fetch()
    new = convert(osm, data["vets"])
    print(f"OSM vets found: {len(osm.get('elements', []))}; new to add: {len(new)}")
    for v in new[:15]:
        print(f"  + {v['name']} ({v['district']})")
    if args.dry_run:
        return
    data["vets"].extend(new)
    DATA.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"Saved. Total vets: {len(data['vets'])}")


if __name__ == "__main__":
    main()
