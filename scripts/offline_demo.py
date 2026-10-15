"""Run the whole app WITHOUT a Gemini key, using simple keyword rules instead of the AI.

For UI work and practice only: the real app uses Gemini for speech, triage and the report.

    python -m scripts.offline_demo     # then open http://localhost:8080
"""

from __future__ import annotations

import uvicorn

from app import ai, safety

KEYWORDS = [
    (("eye", "आँखा", "blurry", "धमिलो"), "ophthalmology"), (("child", "daughter", "son", "छोरी", "छोरा", "बच्चा"), "pediatrics"),
    (("tooth", "दाँत"), "dental"), (("skin", "छाला", "rash", "डाबर"), "dermatology"),
    (("knee", "bone", "हड्डी", "घुँडा", "जोर्नी"), "orthopedics"), (("ear", "कान"), "ent"),
    (("pregnan", "गर्भ"), "obstetrics_gynecology"), (("kidney", "मिर्गौला", "dialysis"), "nephrology"),
    (("heart", "मुटु", "छाती भारी", "chest heavy"), "cardiology"),
]


def fake_triage(text: str) -> ai.Triage:
    low = text.lower()
    emergency = safety.check_text(text)["is_emergency"]
    dept = "emergency" if emergency else next((d for keys, d in KEYWORDS if any(k in low for k in keys)), "general_medicine")
    return ai.Triage(is_health_problem=True, patient="", key_symptoms=[], duration="",
                     urgency="emergency" if emergency else "soon", department=dept, alternative_department="",
                     district_mentioned="", cost_worry=False)


def fake_write_report(**kw) -> ai.ReportText:
    ne = kw["lang"] == "ne"
    label = kw["department_label"]
    return ai.ReportText(
        title=(f"{label}मा जाँच गराउनुहोस् (अफलाइन डेमो)" if ne else f"Visit {label} (offline demo)"),
        summary=("यो अफलाइन डेमो हो। वास्तविक रिपोर्ट Gemini ले लेख्छ।" if ne else "This is the offline demo. Gemini writes the real report."),
        urgency_reason=("तपाईंले भनेका लक्षण अनुसार।" if ne else "Based on what you described."),
        do_now=(["तल दिइएको अस्पतालमा जानुहोस्।", "जानुअघि फोन गरेर पक्का गर्नुहोस्।"] if ne
                else ["Go to the hospital below.", "Call before you travel."]),
        department_reason="",
        picks=[ai.Pick(hospital_id=c["id"], why="") for c in kw["candidates"][:3]],
        what_to_bring=(["नागरिकता वा परिचयपत्र", "पुराना रिपोर्ट", "अहिले खाइरहेको औषधि"] if ne else ["ID card", "Old reports", "Current medicines"]),
        questions_for_doctor=(["कुन जाँच गर्नुपर्छ?"] if ne else ["Which tests do I need?"]),
        warning_signs=(["बेहोस भएमा", "सास फेर्न गाह्रो भएमा"] if ne else ["Fainting", "Severe trouble breathing"]),
        travel_tip="",
    )


ai.triage = fake_triage
ai.write_report = fake_write_report
ai.transcribe = lambda data, mime: "बुवालाई दुई हप्तादेखि हिँड्दा छाती भारी हुन्छ, ६२ वर्ष हुनुभयो।"

from app.main import app  # noqa: E402  (import after patching)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)
