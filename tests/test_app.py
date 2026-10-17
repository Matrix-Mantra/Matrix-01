import json
import shutil
import subprocess

import pytest

from app import ai, config, hospitals, pdf, safety
from tests.conftest import bearer, fake_report_text, fake_triage


# ------------------------------------------------------------------ data


def test_hospital_data_is_consistent():
    rows = hospitals.all_hospitals()
    assert len(rows) >= 60
    vocab = set(hospitals.departments())
    ids = [h["id"] for h in rows]
    assert len(ids) == len(set(ids))
    for h in rows:
        assert set(h["departments"]) <= vocab, h["id"]
        assert 26 < h["lat"] < 31 and 80 < h["lng"] < 89, h["id"]
        assert h["name_ne"], h["id"]
        assert hospitals.resolve_district(h["district"]) == h["district"], h["id"]


def test_billing_has_both_languages_and_all_groups():
    b = hospitals.billing_data()
    for group in ("government", "private", "nonprofit"):
        assert len(b["opd"][group]["en"]) == len(b["opd"][group]["ne"])
    assert len(b["insurance"]["en"]) == len(b["insurance"]["ne"])
    tuth = hospitals.by_id()["tuth"]
    info = hospitals.billing_info(tuth, "ne")
    assert info["group"] == "government" and info["insurance_steps"]
    assert hospitals.billing_info(hospitals.by_id()["grande"], "en")["group"] == "private"
    assert "आकस्मिक" in hospitals.billing_info(tuth, "ne", emergency=True)["steps"][0]


def test_inside_steps_mention_department():
    steps = hospitals.inside_steps(hospitals.by_id()["patan"], "cardiology", "ne")["steps"]
    assert any("मुटु रोग विभाग" in s for s in steps)


def test_map_urls_without_and_with_key(monkeypatch):
    h = hospitals.by_id()["bir"]
    o = {"lat": 27.7, "lng": 85.3, "label": "gps"}
    assert hospitals.map_embed_url(h).startswith("https://maps.google.com/maps?q=27.7046,85.3131")
    assert "t=k" in hospitals.map_embed_url(h, satellite=True)
    assert "origin=27.7%2C85.3" in hospitals.directions_url(h, o)
    monkeypatch.setattr(config, "MAPS_EMBED_API_KEY", "KEY")
    assert hospitals.map_embed_url(h, o).startswith("https://www.google.com/maps/embed/v1/directions?key=KEY")


def test_search_filters_and_distance():
    rows = hospitals.search(q="pokhara")
    assert rows and all(r["district"] == "Kaski" for r in rows)
    assert hospitals.search(q="पाटन")[0]["id"] == "patan"
    o = hospitals.origin_from(district="Banke")
    near = hospitals.search(department="emergency", origin=o, emergency_only=True)
    assert near[0]["district"] == "Banke" and near[0]["distance_km"] < 20


def test_far_specialist_adds_nearest_general():
    c = hospitals.candidates("oncology", hospitals.origin_from(district="Doti"), emergency=False, lang="en")
    assert c["nearest_general"] and c["nearest_general"]["distance_km"] < c["hospitals"][0]["distance_km"]


def test_safety_rules_on_eval_cases():
    cases = json.loads((config.BASE_DIR.parent / "eval" / "cases.json").read_text(encoding="utf-8"))["cases"]
    for c in cases:
        assert safety.check_text(c["text"])["is_emergency"] == c["expect_emergency"], c["id"]


# ------------------------------------------------------------------ public pages


def test_public_endpoints(client):
    assert "Matrix" in client.get("/").text
    cfg = client.get("/api/config").json()
    assert cfg["auth_mode"] == "dev" and cfg["firebase"] is None and "Kathmandu" in cfg["districts"]
    lst = client.get("/api/hospitals", params={"q": "Kathmandu", "lang": "en"}).json()
    assert lst["count"] > 10 and "departments" not in lst["hospitals"][0]
    near = client.get("/api/hospitals", params={"lat": 28.05, "lng": 81.62}).json()["hospitals"]
    assert near[0]["distance_km"] < 10
    d = client.get("/api/hospitals/tuth", params={"lang": "ne"}).json()
    assert d["name_ne"] and d["billing"]["steps"] and d["map_embed_url"] and d["reviews"] == []
    assert client.get("/api/hospitals/nope").status_code == 404


def test_login_required_for_private_actions(client):
    assert client.get("/api/me").status_code == 401
    assert client.post("/api/hospitals/tuth/reviews", json={"rating": 5}).status_code == 401
    assert client.post("/api/report", json={"text": "छाती दुख्यो"}).status_code == 401
    assert client.post("/api/hospitals/tuth/reviews", json={"rating": 5},
                       headers={"Authorization": "Bearer something"}).status_code == 401
    assert client.get("/api/me", headers=bearer("Ram Bahadur Thapa")).json()["name"] == "Ram T."


def test_reviews_flow(client):
    r = client.post("/api/hospitals/tuth/reviews", json={"rating": 4, "comment": "  राम्रो   सेवा  "}, headers=bearer("Sita"))
    assert r.status_code == 200 and r.json()["review"]["comment"] == "राम्रो सेवा"
    client.post("/api/hospitals/tuth/reviews", json={"rating": 2, "comment": "Long wait"}, headers=bearer("Hari"))
    # posting again replaces the user's own review
    client.post("/api/hospitals/tuth/reviews", json={"rating": 5, "comment": "Updated"}, headers=bearer("Sita"))
    d = client.get("/api/hospitals/tuth").json()
    assert d["rating"] == {"avg": 3.5, "count": 2}
    assert {rv["author"] for rv in d["reviews"]} == {"Sita", "Hari"}
    assert all("uid" not in rv for rv in d["reviews"])
    listed = {h["id"]: h for h in client.get("/api/hospitals").json()["hospitals"]}
    assert listed["tuth"]["rating"]["count"] == 2 and listed["bir"]["rating"] is None
    assert client.get("/api/hospitals/tuth/my-review", headers=bearer("Sita")).json()["review"]["rating"] == 5
    assert client.delete("/api/hospitals/tuth/reviews/mine", headers=bearer("Sita")).json()["deleted"]
    assert client.get("/api/hospitals/tuth").json()["rating"]["count"] == 1
    assert client.post("/api/hospitals/tuth/reviews", json={"rating": 6}, headers=bearer()).status_code == 422
    assert client.post("/api/hospitals/tuth/reviews", json={"rating": 3, "comment": "x" * 700},
                       headers=bearer()).status_code == 422


def test_firebase_mode_verifies_token(client, monkeypatch):
    from google.oauth2 import id_token
    monkeypatch.setattr(config, "AUTH_MODE", "firebase")
    monkeypatch.setitem(config.FIREBASE_WEB_CONFIG, "projectId", "proj")
    seen = {}

    def fake_verify(token, request, audience=None):
        seen["aud"] = audience
        if token != "good":
            raise ValueError("bad")
        return {"sub": "uid123", "name": "Maya Gurung", "email": "maya@example.com", "email_verified": True}

    monkeypatch.setattr(id_token, "verify_firebase_token", fake_verify)
    assert client.get("/api/me", headers={"Authorization": "Bearer good"}).json() == {
        "uid": "uid123", "name": "Maya G.", "email": "maya@example.com"}
    # the verified Google email is saved on login, whatever the browser sends
    r = client.post("/api/login", json={"email": "other@example.com"}, headers={"Authorization": "Bearer good"})
    assert r.json()["email"] == "maya@example.com"
    assert seen["aud"] == "proj"
    assert client.get("/api/me", headers={"Authorization": "Bearer bad"}).status_code == 401
    assert client.get("/api/me", headers=bearer()).status_code == 401  # dev tokens rejected in firebase mode


def test_login_saves_user_and_email(client):
    from app.store import get_store
    assert client.post("/api/login", json={"email": "not-an-email"}, headers=bearer("Sita Sharma")).status_code == 422
    r = client.post("/api/login", json={"email": "sita@example.com"}, headers=bearer("Sita Sharma")).json()
    assert r == {"uid": "dev-sita-sharma", "name": "Sita S.", "email": "sita@example.com"}
    client.post("/api/login", json={}, headers=bearer("Sita Sharma"))  # later login without email keeps it
    u = get_store().get_user("dev-sita-sharma")
    assert u["email"] == "sita@example.com" and u["login_count"] == 2
    assert client.get("/api/me", headers=bearer("Sita Sharma")).json()["email"] == "sita@example.com"
    assert client.put("/api/me", json={"email": "new@example.org"}, headers=bearer("Sita Sharma")).json()["email"] == "new@example.org"
    assert client.put("/api/me", json={"email": ""}, headers=bearer("Sita Sharma")).status_code == 422


# ------------------------------------------------------------------ ranking


def test_ranking_scores_and_ties(client):
    from app import ranking
    d = client.get("/api/ranking", params={"lang": "en"}).json()
    rows = d["hospitals"]
    assert len(rows) == d["stats"]["hospitals"] == len(hospitals.all_hospitals())
    assert sum(i["weight"] for i in d["indicators"]) == 100
    assert [r["overall"] for r in rows] == sorted((r["overall"] for r in rows), reverse=True)
    assert rows[0]["rank"] == 1 and all(0 <= r["overall"] <= 100 for r in rows)
    for a, b in zip(rows, rows[1:]):  # equal scores share a rank, QS style
        assert (b["rank"] == a["rank"]) == (b["overall"] == a["overall"])
        assert b["tied"] or b["rank"] != a["rank"]
    assert all(r["scores"]["rating"] is None for r in rows)  # no reviews yet -> pending, weight re-shared
    s = {"specialties": 50.0, "emergency": 100.0, "insurance": 0.0, "teaching": 0.0, "rating": None}
    assert ranking.overall(s) == round((50 * 35 + 100 * 20) / 80, 1)


def test_ranking_counts_ratings_after_min_reviews(client):
    for i, name in enumerate(["A One", "B Two", "C Three"]):
        client.post("/api/hospitals/bir/reviews", json={"rating": 5}, headers=bearer(name))
        bir = next(r for r in client.get("/api/ranking").json()["hospitals"] if r["id"] == "bir")
        assert (bir["scores"]["rating"] == 100.0) == (i == 2)


# ------------------------------------------------------------------ report pipeline


def test_report_pipeline_grounded(client, monkeypatch):
    calls = {}

    def fake_write(**kw):
        calls.update(kw)
        ids = [c["id"] for c in kw["candidates"]]
        return fake_report_text(["invented_hospital", ids[1], ids[0], ids[1]])

    monkeypatch.setattr(ai, "triage", lambda text: fake_triage())
    monkeypatch.setattr(ai, "write_report", fake_write)
    client.post("/api/hospitals/bir/reviews", json={"rating": 5}, headers=bearer("A"))
    r = client.post("/api/report", json={"text": "बुवालाई हिँड्दा थकाइ लाग्छ, मुटुको जाँच गर्नुपर्छ", "lang": "ne",
                                         "district": "Kathmandu"}, headers=bearer())
    assert r.status_code == 200, r.text
    rep = r.json()
    assert rep["department"] == "cardiology" and rep["urgency"] == "soon"
    ids = [h["id"] for h in rep["hospitals"]]
    assert "invented_hospital" not in ids and len(ids) == len(set(ids)) == 2
    h0 = rep["hospitals"][0]
    assert h0["billing"]["steps"] and h0["inside"]["steps"] and h0["directions_url"].startswith("https://www.google.com/maps/dir/")
    assert "origin=" in h0["directions_url"] and h0["distance_km"] is not None
    assert all("cardiology" in hospitals.by_id()[i]["departments"] for i in ids)
    # ratings are passed to the model as context
    assert any(c.get("rating") for c in calls["candidates"])
    assert rep["department_label"] == "मुटु रोग विभाग" and rep["disclaimer"]


def test_safety_overrides_model(client, monkeypatch):
    monkeypatch.setattr(ai, "triage", lambda text: fake_triage(urgency="routine", department="dermatology"))
    monkeypatch.setattr(ai, "write_report", lambda **kw: fake_report_text([kw["candidates"][0]["id"]]))
    rep = client.post("/api/report", json={"text": "my father has chest pain and sweating", "lang": "en",
                                           "lat": 27.70, "lng": 85.32}, headers=bearer()).json()
    assert rep["urgency"] == "emergency" and rep["department"] == "emergency"
    assert rep["safety_flags"] and rep["hospitals"][0]["emergency_24h"]
    assert rep["hospitals"][0]["billing"]["steps"][0].startswith("Go straight to the emergency")


def test_district_from_speech_used_when_no_location(client, monkeypatch):
    monkeypatch.setattr(ai, "triage", lambda text: fake_triage(department="pediatrics", district_mentioned="Dang"))
    monkeypatch.setattr(ai, "write_report", lambda **kw: fake_report_text([kw["candidates"][0]["id"]]))
    rep = client.post("/api/report", json={"text": "छोरीलाई तीन दिनदेखि ज्वरो छ, दाङमा बस्छौं", "lang": "ne"},
                      headers=bearer()).json()
    assert rep["origin"]["label"] == "Dang" and rep["hospitals"][0]["district"] == "Dang"


def test_not_health_related(client, monkeypatch):
    monkeypatch.setattr(ai, "triage", lambda text: fake_triage(is_health_problem=False))
    r = client.post("/api/report", json={"text": "what is the weather today"}, headers=bearer())
    assert r.status_code == 422


def test_ai_failure_still_returns_safety(client, monkeypatch):
    def boom(text):
        raise RuntimeError("no key")

    monkeypatch.setattr(ai, "triage", boom)
    r = client.post("/api/report", json={"text": "सास फेर्न गाह्रो भयो"}, headers=bearer())
    assert r.status_code == 502 and r.json()["safety"]["is_emergency"]


def test_daily_limit(client, monkeypatch):
    monkeypatch.setattr(config, "DAILY_REPORT_LIMIT", 1)
    monkeypatch.setattr(ai, "triage", lambda text: fake_triage())
    monkeypatch.setattr(ai, "write_report", lambda **kw: fake_report_text([kw["candidates"][0]["id"]]))
    assert client.post("/api/report", json={"text": "knee pain"}, headers=bearer()).status_code == 200
    assert client.post("/api/report", json={"text": "knee pain"}, headers=bearer()).status_code == 429


def test_transcribe(client, monkeypatch):
    monkeypatch.setattr(ai, "transcribe", lambda data, mime: "छाती दुख्यो")
    r = client.post("/api/transcribe", files={"audio": ("a.webm", b"x" * 2000, "audio/webm")}, headers=bearer())
    assert r.json()["text"] == "छाती दुख्यो" and r.json()["safety"]["is_emergency"]
    assert client.post("/api/transcribe", files={"audio": ("a.webm", b"x", "audio/webm")}, headers=bearer()).status_code == 400
    assert client.post("/api/transcribe", files={"audio": ("a.webm", b"x" * 2000, "audio/webm")}).status_code == 401


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg missing")
def test_webm_to_wav(tmp_path):
    src = tmp_path / "t.webm"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
                    "-c:a", "libopus", str(src)], check=True)
    data, mime = ai.to_supported_audio(src.read_bytes(), "audio/webm;codecs=opus")
    assert mime == "audio/wav" and data[:4] == b"RIFF"


# ------------------------------------------------------------------ PDF


def _report_for_pdf(client, monkeypatch, lang="ne"):
    monkeypatch.setattr(ai, "triage", lambda text: fake_triage())
    monkeypatch.setattr(ai, "write_report", lambda **kw: fake_report_text(
        [c["id"] for c in kw["candidates"][:3]], title="मुटु रोग विभागमा जानुहोस्", summary="बुवालाई छाती दुखेको छ।"))
    return client.post("/api/report", json={"text": "बुवालाई हिँड्दा छाती भारी हुन्छ", "lang": lang,
                                            "district": "Kathmandu"}, headers=bearer()).json()


def test_pdf_download(client, monkeypatch, tmp_path):
    rep = _report_for_pdf(client, monkeypatch)
    r = client.post("/api/report/pdf", json=rep, headers=bearer())
    assert r.status_code == 200 and r.content[:4] == b"%PDF"
    assert "attachment" in r.headers["content-disposition"]
    if shutil.which("pdftotext"):
        f = tmp_path / "r.pdf"
        f.write_bytes(r.content)
        text = subprocess.run(["pdftotext", str(f), "-"], capture_output=True, text=True).stdout
        assert rep["hospitals"][0]["name"] in text
    assert client.post("/api/report/pdf", json=rep).status_code == 401


def test_pdf_rejects_tampered_links(client, monkeypatch):
    rep = _report_for_pdf(client, monkeypatch)
    rep["hospitals"][0]["directions_url"] = "file:///etc/passwd"
    assert client.post("/api/report/pdf", json=rep, headers=bearer()).status_code == 422


def test_pdf_html_escapes_text(client, monkeypatch):
    rep = _report_for_pdf(client, monkeypatch, lang="en")
    rep["summary"] = '<img src="file:///etc/passwd">'
    html = pdf.render_html(rep)
    assert "&lt;img" in html and '<img src="file:///etc/passwd">' not in html


def test_list_sorted_from_saved_district(client):
    rows = client.get("/api/hospitals", params={"near": "Kaski"}).json()["hospitals"]
    assert rows[0]["district"] == "Kaski" and rows[0]["distance_km"] < 5


def test_email_report(client, monkeypatch, tmp_path):
    import email
    rep = _report_for_pdf(client, monkeypatch)
    monkeypatch.setattr(config, "SMTP_HOST", "")
    monkeypatch.setattr(config, "MAIL_OUTBOX", "")
    assert client.post("/api/report/email", json=rep, headers=bearer()).status_code == 503
    monkeypatch.setattr(config, "MAIL_OUTBOX", str(tmp_path / "outbox"))
    assert client.get("/api/config").json()["email_enabled"]
    assert client.post("/api/report/email", json=rep, headers=bearer()).status_code == 400  # no email saved yet
    client.post("/api/login", json={"email": "sita@example.com"}, headers=bearer())
    r = client.post("/api/report/email", json=rep, headers=bearer())
    assert r.status_code == 200 and r.json() == {"sent_to": "sita@example.com", "delivered": False}
    [eml] = list((tmp_path / "outbox").glob("*.eml"))
    msg = email.message_from_bytes(eml.read_bytes())
    assert msg["To"] == "sita@example.com"
    att = [p for p in msg.walk() if p.get_content_type() == "application/pdf"]
    assert att and att[0].get_payload(decode=True)[:4] == b"%PDF"
    assert client.post("/api/report/email", json=rep).status_code == 401


# ------------------------------------------------------------------ animals → vets

RABBIT = "मेरो खरायोले कति दिन भयो केही पनि नखाको, एउटै ठाउँमा मात्रै बसिराख्छ। एनिमल हस्पिटल कतै छ त?"


def test_animal_safety_rules():
    assert safety.animal_mentioned(RABBIT) == "rabbit"
    assert [f["id"] for f in safety.check_animal(RABBIT)["flags"]] == ["animal_not_eating_small"]
    assert safety.banner_check(RABBIT)["subject"] == "animal"
    # a bite on a person stays a human case (rabies)
    assert safety.animal_bite("कुकुरले छोरालाई टोक्यो") and safety.animal_mentioned("कुकुरले छोरालाई टोक्यो") == ""
    # human red flags always keep the human banner with "Call 102"
    b = safety.banner_check("मेरो छोरालाई छाती दुख्यो, कुकुर देखेर डरायो")
    assert b["subject"] == "person" and b["is_emergency"]


def _fake_vet_text(picks):
    return ai.VetReportText(title="Rabbit not eating", summary="S.", urgency_reason="R.", do_now=["Go to a vet today"],
                            care_at_home=["Keep it warm"], food_tips=["Hay"], picks=[ai.VetPick(vet_id=p, why="near")
                                                                                       for p in picks],
                            tell_the_vet=["When it stopped eating"], warning_signs=["Cannot stand"], travel_tip="")


def test_animal_report_uses_real_vets(client, monkeypatch):
    from app import vets
    seen = {}
    monkeypatch.setattr(ai, "triage", lambda text: fake_triage(subject="animal", animal="rabbit", urgency="soon"))

    def fake_write(**kw):
        seen.update(kw)
        return _fake_vet_text(["made-up-clinic", kw["candidates"][0]["id"]])

    monkeypatch.setattr(ai, "write_vet_report", fake_write)
    r = client.post("/api/report", json={"text": RABBIT, "lang": "ne", "district": "Kathmandu"}, headers=bearer()).json()
    assert r["kind"] == "animal" and r["animal_label"] == "खरायो"
    assert r["urgency"] == "urgent"  # the rule raises "soon" to "see a vet today"
    ids = {v["id"] for v in vets.all_vets()}
    assert r["hospitals"] and all(h["id"] in ids for h in r["hospitals"])  # invented clinic dropped
    assert all(h["distance_km"] <= vets.MAX_KM for h in seen["candidates"])
    assert r["district_office"]["name"].endswith("Kathmandu")
    assert r["vet_search_url"].startswith("https://www.google.com/maps/search/")
    pdf_r = client.post("/api/report/pdf", json=r, headers=bearer())
    assert pdf_r.status_code == 200 and pdf_r.content[:4] == b"%PDF"
    bad = {**r, "vet_search_url": "https://evil.example/"}
    assert client.post("/api/report/pdf", json=bad, headers=bearer()).status_code == 422


def test_animal_bite_on_person_stays_human(client, monkeypatch):
    called = {}
    monkeypatch.setattr(ai, "triage", lambda text: fake_triage(subject="animal", animal="dog", department="emergency"))
    monkeypatch.setattr(ai, "write_vet_report", lambda **kw: called.setdefault("vet", True))
    monkeypatch.setattr(ai, "write_report", lambda **kw: fake_report_text([kw["candidates"][0]["id"]]))
    r = client.post("/api/report", json={"text": "कुकुरले छोरालाई टोक्यो", "district": "Kathmandu"}, headers=bearer()).json()
    assert "vet" not in called and r.get("kind") != "animal" and r["department"] == "emergency"

