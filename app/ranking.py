"""QS-style ranking of every hospital we list, scored only from data the app has.

The scores describe what is *listed* about a hospital (services, access, ratings), not the quality of its care.
Each indicator is 0-100; the overall score is their weighted average.

Patient rating is a Bayesian average: every hospital starts as if it had PRIOR_REVIEWS reviews of PRIOR_STARS
(neutral), and real reviews pull it toward their true average. A handful of reviews (fake or real) moves the score
only a little, and there is no review-count cliff to aim for. A fixed neutral prior is used rather than the average
across all hospitals, because while reviews are few that site-wide average could itself be rigged.
"""

from __future__ import annotations

from . import hospitals

PRIOR_REVIEWS = 10
PRIOR_STARS = 3.0

# key, weight (%)
INDICATORS = [
    ("specialties", 35),  # number of departments, relative to the hospital with the most
    ("emergency", 20),    # 24-hour emergency department
    ("insurance", 15),    # accepts the national health insurance
    ("teaching", 10),     # teaching hospital 100, specialty centre 50, other 0
    ("rating", 20),       # average patient rating (1-5 stars mapped to 0-100)
]


def type_group(t: str) -> str:
    """The four groups the ranking filter offers."""
    if "teaching" in t:
        return "teaching"
    if t.startswith("government"):
        return "government"
    if t.startswith("private"):
        return "private"
    return "community"


def _teaching_score(t: str) -> float:
    if "teaching" in t:
        return 100.0
    if "specialty" in t:
        return 50.0
    return 0.0


def rating_score(rating: dict | None) -> float:
    """Bayesian average of the stars, mapped from 1-5 to 0-100. No reviews -> the neutral prior (50)."""
    n = rating.get("count", 0) if rating else 0
    stars = (n * rating["avg"] + PRIOR_REVIEWS * PRIOR_STARS) / (n + PRIOR_REVIEWS) if n else PRIOR_STARS
    return round((stars - 1) / 4 * 100, 1)


def indicator_scores(h: dict, max_depts: int, rating: dict | None) -> dict[str, float | None]:
    return {
        "specialties": round(100 * len(h.get("departments", [])) / max_depts, 1) if max_depts else 0.0,
        "emergency": 100.0 if h.get("emergency_24h") else 0.0,
        "insurance": 100.0 if h.get("health_insurance") else 0.0,
        "teaching": _teaching_score(h.get("type", "")),
        "rating": rating_score(rating),
    }


def overall(scores: dict[str, float | None]) -> float:
    used = [(scores[k], w) for k, w in INDICATORS if scores[k] is not None]
    return round(sum(s * w for s, w in used) / sum(w for _, w in used), 1)


def build(ratings: dict[str, dict], lang: str = "en") -> list[dict]:
    """All hospitals, best first, with QS-style tied ranks ("=4")."""
    rows = hospitals.all_hospitals()
    max_depts = max((len(h.get("departments", [])) for h in rows), default=0)
    out = []
    for h in rows:
        scores = indicator_scores(h, max_depts, ratings.get(h["id"]))
        out.append({
            "id": h["id"], "name": h["name"], "name_ne": h.get("name_ne"), "city": h.get("city"),
            "district": h.get("district"), "province": h.get("province"), "type_group": type_group(h.get("type", "")),
            "type_label": hospitals.type_label(h.get("type", "unknown"), lang),
            "departments": len(h.get("departments", [])), "emergency_24h": bool(h.get("emergency_24h")),
            "health_insurance": bool(h.get("health_insurance")), "verified": bool(h.get("verified")),
            "rating": ratings.get(h["id"]), "scores": scores, "overall": overall(scores),
        })
    out.sort(key=lambda r: (-r["overall"], r["name"]))
    for i, r in enumerate(out):
        if i and r["overall"] == out[i - 1]["overall"]:
            r["rank"] = out[i - 1]["rank"]
        else:
            r["rank"] = i + 1
    counts: dict[int, int] = {}
    for r in out:
        counts[r["rank"]] = counts.get(r["rank"], 0) + 1
    for r in out:
        r["tied"] = counts[r["rank"]] > 1
    return out
