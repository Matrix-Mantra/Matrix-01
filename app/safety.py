"""Deterministic red-flag detection.

This layer runs in plain Python on every message BEFORE the AI model sees it,
so an emergency is never left to the model alone. It deliberately prefers
false alarms over missed emergencies (e.g. "no chest pain" still triggers).

Phrases cover English, Nepali (Devanagari) and common romanized Nepali.
Have a clinician review this list before launch.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class RedFlagRule:
    id: str
    label_en: str
    label_ne: str
    # Rule fires if ANY phrase in `any_of` appears ...
    any_of: tuple[str, ...] = ()
    # ... OR if, for every group in `all_groups`, at least one phrase appears.
    all_groups: tuple[tuple[str, ...], ...] = field(default_factory=tuple)
    action_en: str = "Call 102 for an ambulance or go to the nearest emergency department now."
    action_ne: str = "अहिले नै १०२ मा फोन गरी एम्बुलेन्स बोलाउनुहोस् वा नजिकको आकस्मिक कक्षमा जानुहोस्।"


RULES: tuple[RedFlagRule, ...] = (
    RedFlagRule(
        id="chest_pain",
        label_en="Chest pain or pressure",
        label_ne="छाती दुखाइ वा छाती थिचिएको जस्तो",
        any_of=(
            "chest pain", "chest tightness", "pain in chest", "pressure in chest", "heart attack",
            "छाती दुख", "छातीमा दुख", "छाती पोल", "छाती कस", "मुटुको दौरा", "हार्ट अट्याक",
            "chhati dukh", "chati dukh", "chhatima dukh", "chatima dukh",
        ),
    ),
    RedFlagRule(
        id="breathing",
        label_en="Severe difficulty breathing",
        label_ne="सास फेर्न धेरै गाह्रो",
        any_of=(
            "can't breathe", "cannot breathe", "can not breathe", "difficulty breathing",
            "trouble breathing", "shortness of breath", "breathless", "not breathing", "choking",
            "सास फेर्न गाह्रो", "सास फेर्न सकेन", "सास फेर्न सक्दैन", "सास रोकि", "सास बढ", "निसास्सिए",
            "saas pherna garo", "sas ferna garo", "saas fernu garo", "sas pherna garo",
        ),
    ),
    RedFlagRule(
        id="unconscious",
        label_en="Unconscious, fainted or not responding",
        label_ne="बेहोस वा प्रतिक्रिया नदिने",
        any_of=(
            "unconscious", "fainted", "passed out", "not responding", "unresponsive", "collapsed",
            "बेहोस", "होस छैन", "ढलेको", "ढल्यो",
            "behosh", "behos", "hos chaina",
        ),
    ),
    RedFlagRule(
        id="seizure",
        label_en="Seizure / fits",
        label_ne="छारे रोग / काम्ने दौरा",
        any_of=(
            "seizure", "convulsion", "fits", "fitting",
            "छारे", "मिर्गी", "कम्प छुट", "दौरा पर्",
            "chhare", "chare rog", "mirgi",
        ),
    ),
    RedFlagRule(
        id="stroke",
        label_en="Possible stroke (face drooping, weakness on one side, slurred speech)",
        label_ne="पक्षघातको लक्षण (अनुहार बाङ्गिने, एक भाग कमजोर, बोली लरबराउने)",
        any_of=(
            "stroke", "face drooping", "face is drooping", "slurred speech", "one side weak",
            "weakness on one side", "can't move one side", "paralysis", "paralyzed",
            "पक्षघात", "प्यारालाइसिस", "मुख बाङ्गो", "अनुहार बाङ्गो", "बोली लर", "आधा जिउ",
            "pakshaghat", "mukh bango", "boli lar",
        ),
    ),
    RedFlagRule(
        id="severe_bleeding",
        label_en="Heavy bleeding",
        label_ne="धेरै रगत बगिरहेको",
        any_of=(
            "heavy bleeding", "bleeding a lot", "won't stop bleeding", "bleeding heavily",
            "vomiting blood", "coughing blood", "blood in vomit",
            "धेरै रगत", "रगत रोकिएन", "रगत बान्ता", "रगत खकार",
            "dherai ragat", "ragat rokiyena", "ragat banta",
        ),
    ),
    RedFlagRule(
        id="pregnancy_danger",
        label_en="Danger sign in pregnancy",
        label_ne="गर्भावस्थामा खतराको संकेत",
        all_groups=(
            ("pregnan", "गर्भ", "garbha", "pet ma bachcha", "पेटमा बच्चा", "sutkeri", "सुत्केरी", "delivery", "labor", "labour"),
            ("bleed", "रगत", "ragat", "severe pain", "धेरै दुख", "fit", "छारे", "swelling", "सुन्निए", "blurred vision",
             "headache", "टाउको दुख", "water broke", "पानी फुट", "baby not moving", "बच्चा चलेन"),
        ),
    ),
    RedFlagRule(
        id="snake_bite",
        label_en="Snake bite",
        label_ne="सर्पदंश",
        any_of=(
            "snake bite", "snakebite", "bitten by a snake", "snake bit",
            "सर्पले टोक", "सर्पदंश", "सर्प टोक",
            "sarpa le tok", "sarpale tok", "sap le tok", "saap le tok",
        ),
        action_en="Keep the person still, do not cut or suck the wound, and go to the nearest hospital or snakebite treatment centre now (call 102).",
        action_ne="बिरामीलाई नचलाउनुहोस्, घाउ नकाट्नुहोस् वा नचुस्नुहोस्, र तुरुन्तै नजिकको अस्पताल वा सर्पदंश उपचार केन्द्र जानुहोस् (१०२)।",
    ),
    RedFlagRule(
        id="poisoning",
        label_en="Poisoning or overdose",
        label_ne="विष वा औषधि धेरै खाएको",
        any_of=(
            "poison", "pesticide", "overdose", "swallowed chemical", "drank kerosene",
            "विष", "बिष", "किटनाशक", "विषादी", "धेरै औषधि खा",
            "bish", "bis khayo", "bisadi",
        ),
    ),
    RedFlagRule(
        id="self_harm",
        label_en="Thoughts of suicide or self-harm",
        label_ne="आत्महत्या वा आफूलाई हानि गर्ने विचार",
        any_of=(
            "suicide", "kill myself", "want to die", "end my life", "self harm", "self-harm", "hurt myself",
            "आत्महत्या", "मर्न मन", "बाँच्न मन छैन", "आफैलाई मार",
            "atmahatya", "marna man", "banchna man chaina",
        ),
        action_en="You are not alone. If you are in danger right now, call 102 or go to the nearest emergency department, and reach out to someone you trust.",
        action_ne="तपाईं एक्लै हुनुहुन्न। अहिले नै खतरा छ भने १०२ मा फोन गर्नुहोस् वा नजिकको आकस्मिक कक्षमा जानुहोस्, र विश्वास लाग्ने कसैसँग कुरा गर्नुहोस्।",
    ),
    RedFlagRule(
        id="severe_burn",
        label_en="Serious burn",
        label_ne="गम्भीर रूपमा पोलेको",
        any_of=(
            "severe burn", "badly burned", "burnt badly", "burned face", "electric shock",
            "नराम्ररी पोल", "आगोले पोल", "करेन्ट लाग",
            "naramrari pol", "current lagyo",
        ),
    ),
    RedFlagRule(
        id="head_injury",
        label_en="Serious head injury",
        label_ne="टाउकोमा गम्भीर चोट",
        all_groups=(
            ("head injury", "hit head", "hit his head", "hit her head", "fell on head", "टाउकोमा चोट", "टाउको फुट", "tauko ma chot", "tauko phut"),
            ("vomit", "बान्ता", "banta", "sleepy", "निदाउ", "confus", "bleeding", "रगत", "ragat", "unconscious", "बेहोस", "behosh"),
        ),
    ),
    RedFlagRule(
        id="infant_danger",
        label_en="Danger sign in a baby",
        label_ne="शिशुमा खतराको संकेत",
        all_groups=(
            ("baby", "infant", "newborn", "शिशु", "नवजात", "सानो बच्चा", "nani", "नानी", "bachcha", "बच्चा"),
            ("not feeding", "not breastfeeding", "won't feed", "दूध खाँदैन", "दूध चुस्दैन", "blue", "निलो",
             "very high fever", "fever and fits", "limp", "lethargic", "जिउ गल", "दूध खादैन", "dudh khadaina"),
        ),
    ),
)


def _normalize(text: str) -> str:
    text = text.lower()
    text = text.replace("’", "'")
    text = re.sub(r"\s+", " ", text)
    return text


def _has(phrase: str, norm: str) -> bool:
    """Latin phrases must start at a word boundary ("fits" must not match "benefits");
    Devanagari phrases match as substrings because Nepali attaches suffixes (छातीमा, छातीको)."""
    if phrase.isascii():
        return re.search(r"(?<![a-z])" + re.escape(phrase), norm) is not None
    return phrase in norm


def check_text(text: str) -> dict:
    """Return the red flags found in `text`.

    Result shape:
        {"is_emergency": bool, "flags": [{"id", "label_en", "label_ne", "action_en", "action_ne"}]}
    """
    norm = _normalize(text or "")
    hits = []
    for rule in RULES:
        fired = any(_has(p, norm) for p in rule.any_of)
        if not fired and rule.all_groups:
            fired = all(any(_has(p, norm) for p in group) for group in rule.all_groups)
        if fired:
            hits.append(
                {
                    "id": rule.id,
                    "label_en": rule.label_en,
                    "label_ne": rule.label_ne,
                    "action_en": rule.action_en,
                    "action_ne": rule.action_ne,
                }
            )
    return {"is_emergency": bool(hits), "flags": hits}
