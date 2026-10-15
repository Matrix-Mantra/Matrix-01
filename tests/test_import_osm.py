from app import hospitals
from scripts import import_osm

SAMPLE = {"elements": [
    # duplicate of an existing hospital by name -> skipped
    {"type": "node", "id": 1, "lat": 27.70, "lon": 85.31, "tags": {"amenity": "hospital", "name": "Bir Hospital (NAMS)"}},
    # within 300 m of an existing hospital -> skipped
    {"type": "node", "id": 2, "lat": 27.7361, "lon": 85.3304, "tags": {"amenity": "hospital", "name": "Some Clinic Block"}},
    # new, way with centre
    {"type": "way", "id": 3, "center": {"lat": 28.84, "lon": 81.72}, "tags": {
        "amenity": "hospital", "name": "Dailekh District Hospital", "name:ne": "दैलेख जिल्ला अस्पताल",
        "operator:type": "government", "emergency": "yes", "phone": "+977-89-000000"}},
    # no name -> skipped
    {"type": "node", "id": 4, "lat": 27.0, "lon": 85.0, "tags": {"amenity": "hospital"}},
]}


def test_convert_dedupes_and_maps_fields():
    new = import_osm.convert(SAMPLE, hospitals.all_hospitals())
    assert [h["id"] for h in new] == ["osm-w3"]
    h = new[0]
    assert h["type"] == "government" and h["emergency_24h"] is True and h["departments"] == []
    assert h["name_ne"] == SAMPLE["elements"][2]["tags"]["name:ne"] and h["district"] == "Dailekh"
    assert h["source_url"] == "https://www.openstreetmap.org/way/3" and h["verified"] is False
    assert hospitals.type_label(h["type"], "en") == "Government hospital"
