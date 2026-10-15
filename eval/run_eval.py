"""Evaluate the safety rules and the Gemini triage step on eval/cases.json.

    python -m eval.run_eval          # safety rules only (offline, no key)
    python -m eval.run_eval --live   # also run every case through Gemini triage

Writes eval/results.md. Put the headline numbers on the "Safety and evaluation" slide.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from app import ai, safety

HERE = Path(__file__).resolve().parent


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true")
    args = ap.parse_args()
    cases = json.loads((HERE / "cases.json").read_text(encoding="utf-8"))["cases"]
    em = [c for c in cases if c["expect_emergency"]]
    caught = sum(safety.check_text(c["text"])["is_emergency"] for c in em)
    false_alarms = sum(safety.check_text(c["text"])["is_emergency"] for c in cases if not c["expect_emergency"])
    lines = ["# Evaluation results", "", f"Cases: {len(cases)} ({len(em)} emergencies)", "",
             "## Safety rules (code)", f"- Emergencies caught: **{caught}/{len(em)}**",
             f"- False alarms: **{false_alarms}/{len(cases) - len(em)}**", ""]
    print(f"Safety rules: caught {caught}/{len(em)}, false alarms {false_alarms}")

    if args.live:
        rows, times = [], []
        for c in cases:
            t0 = time.time()
            try:
                tri = ai.triage(c["text"])
                urgency = "emergency" if safety.check_text(c["text"])["is_emergency"] else tri.urgency
                dept = "emergency" if urgency == "emergency" else tri.department
                err = ""
            except Exception as exc:  # keep going
                tri, urgency, dept, err = None, "", "", str(exc)[:80]
            times.append(time.time() - t0)
            ok_dept = dept in c["accept_departments"]
            ok_urg = (urgency == "emergency") == c["expect_emergency"]
            model_urg = tri.urgency if tri else ""
            rows.append((c["id"], dept, urgency, model_urg, ok_dept, ok_urg, err))
            print(f"{c['id']}: {dept} {urgency} (model said {model_urg}) {'ok' if ok_dept else 'DEPT MISS'} "
                  f"{'ok' if ok_urg else 'URGENCY MISS'} {err}")
        n = len(rows)
        model_alone = sum((r[3] == "emergency") for r in rows if r[0].startswith("e"))
        lines += ["## Gemini triage + safety rules", f"- Department correct: **{sum(r[4] for r in rows)}/{n}**",
                  f"- Emergency decision correct: **{sum(r[5] for r in rows)}/{n}**",
                  f"- Emergencies the model flagged on its own (before code rules): **{model_alone}/{len(em)}**",
                  f"- Median time per case: **{sorted(times)[n // 2]:.1f} s**", "",
                  "| Case | Department | Urgency | Model urgency | Dept OK | Urgency OK |", "| --- | --- | --- | --- | --- | --- |"]
        lines += [f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} | {'yes' if r[4] else 'NO'} | {'yes' if r[5] else 'NO'} |" for r in rows]
    (HERE / "results.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {HERE / 'results.md'}")


if __name__ == "__main__":
    main()
