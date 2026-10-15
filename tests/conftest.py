import pytest
from fastapi.testclient import TestClient

from app import ai, config, store


@pytest.fixture(autouse=True)
def fresh_store(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "SQLITE_PATH", str(tmp_path / "test.db"))
    monkeypatch.setattr(config, "STORE", "sqlite")
    monkeypatch.setattr(config, "AUTH_MODE", "dev")
    store.get_store.cache_clear()
    from app import auth
    auth._usage.clear()
    yield
    store.get_store.cache_clear()


@pytest.fixture
def client():
    from app.main import app
    return TestClient(app)


def bearer(name="Sita Sharma"):
    return {"Authorization": f"Bearer dev:{name}"}


def fake_triage(**over):
    base = dict(is_health_problem=True, patient="father, 62", key_symptoms=["chest pain"], duration="2 days",
                urgency="soon", department="cardiology", alternative_department="general_medicine",
                district_mentioned="", cost_worry=False)
    base.update(over)
    return ai.Triage(**base)


def fake_report_text(picks, **over):
    base = dict(title="Go to cardiology", summary="Summary.", urgency_reason="Because.", do_now=["Step 1", "Step 2"],
                department_reason="Heart problems are seen in cardiology.",
                picks=[ai.Pick(hospital_id=h, why=f"why {h}") for h in picks],
                what_to_bring=["ID card"], questions_for_doctor=["What tests?"], warning_signs=["Fainting"],
                travel_tip="Leave early.")
    base.update(over)
    return ai.ReportText(**base)
