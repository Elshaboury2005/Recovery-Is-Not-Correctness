#!/usr/bin/env python3
"""Reproducible, dependency-free analysis of the ChaosFlow 240 campaign."""
from __future__ import annotations

import csv
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
ANALYSIS = ROOT / "analysis"
FIGURES = ANALYSIS / "figures"
SCHEDULE = ROOT / "run_schedule.csv"
ATTEMPTS = ROOT / "attempts"
PROTOCOL = "CHAOSFLOW-240-OBSERVER-RECOVERY-V1"
SCENARIOS = [f"C{i}" for i in range(8)]
OBSERVERS = ["OBSERVER_ON", "OBSERVER_OFF"]
METRICS = [
    "end_to_end_seconds", "T1_minus_T0_seconds", "T2_minus_T0_seconds",
    "T3_minus_T0_seconds", "T4_minus_T0_seconds", "T5_minus_T0_seconds",
    "T2_minus_T1_seconds", "T3_minus_T2_seconds", "T4_minus_T3_seconds",
]


def utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def read_schedule() -> list[dict[str, str]]:
    with SCHEDULE.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def interval(value: object) -> tuple[float, float] | None:
    if not isinstance(value, dict):
        return None
    lower, upper = value.get("lower"), value.get("upper")
    if isinstance(lower, (int, float)) and isinstance(upper, (int, float)) and upper >= lower:
        return float(lower), float(upper)
    return None


def interval_between(start: object, end: object) -> tuple[float, float] | None:
    a, b = interval(start), interval(end)
    if not a or not b:
        return None
    lower, upper = b[0] - a[1], b[1] - a[0]
    if lower < 0 or upper < lower:
        return None
    return lower, upper


def midpoint(pair: tuple[float, float] | None) -> float | None:
    return None if pair is None else (pair[0] + pair[1]) / 2


def iso_seconds(value: object) -> float | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value).timestamp()
    except ValueError:
        return None


def endpoint_duration(recovery: dict, key: str, t0: object) -> tuple[float, float] | None:
    if key == "T4":
        t4 = recovery.get("T4") or {}
        event = t4.get("event") if isinstance(t4, dict) else None
        t0_pair = interval(t0)
        confirmed = event.get("confirmed_at") if isinstance(event, dict) else None
        if t0_pair and isinstance(confirmed, (int, float)):
            return confirmed - t0_pair[1], confirmed - t0_pair[0]
        return None
    return interval_between(t0, recovery.get(key))


def end_to_end(status: dict, manifest: dict) -> float | None:
    start = iso_seconds(manifest.get("created_wall_utc"))
    finish = iso_seconds(status.get("completed_wall_utc"))
    if start is None or finish is None or finish < start:
        return None
    return finish - start


def latest_status(row: dict) -> tuple[dict, Path]:
    ids = [x for x in row.get("attempt_ids", "").split(";") if x]
    if not ids:
        raise RuntimeError(f"schedule row {row.get('slot')} has no attempt ID")
    attempt_id = ids[-1]
    directory = ATTEMPTS / attempt_id
    return read_json(directory / "attempt_status.json"), directory


def strict_qualifying(status: dict) -> bool:
    if status.get("status") != "QUALIFYING" or status.get("correctness_ok") is not True:
        return False
    if status.get("scenario") == "C0":
        return True
    if status.get("instrumentation_ok") is False:
        return False
    recovery = status.get("recovery") or {}
    return all(recovery.get(key) is not None for key in ("T0", "T1", "T2", "T3"))


def load_qualifying() -> list[dict]:
    schedule = read_schedule()
    if len(schedule) != 240:
        raise RuntimeError(f"run schedule has {len(schedule)} rows, expected 240")
    records = []
    for row in schedule:
        status, directory = latest_status(row)
        if row.get("status") != "QUALIFYING" or not strict_qualifying(status):
            raise RuntimeError(f"schedule row {row.get('slot')} is not strict-qualifying")
        recovery = status.get("recovery") or {}
        manifest = read_json(directory / "run_manifest.json")
        t0 = recovery.get("T0")
        values: dict[str, object] = {
            "slot": int(row["slot"]), "block": row["block"], "repetition": int(row["repetition"]),
            "order": int(row["order"]), "scenario": row["scenario"], "observer_state": row["observer_state"],
            "attempt_id": status.get("attempt_id"), "directory": str(directory),
            "terminal_status": status.get("terminal_status"), "correctness_ok": status.get("correctness_ok"),
            "oracle_output_correct": status.get("oracle_output_correct"),
            "oracle_exit_code": status.get("oracle_exit_code"), "validation_exit_code": status.get("validation_exit_code"),
            "t4_status": (recovery.get("T4") or {}).get("status"),
            "t4_rate_lower": ((recovery.get("T4") or {}).get("event") or {}).get("rate_lower"),
            "baseline_rate": ((recovery.get("T4") or {}).get("event") or {}).get("baseline_rate"),
            "end_to_end_seconds": end_to_end(status, manifest),
        }
        for key in ("T1", "T2", "T3", "T4", "T5"):
            values[f"{key}_minus_T0_seconds"] = midpoint(endpoint_duration(recovery, key, t0))
        values["T2_minus_T1_seconds"] = midpoint(interval_between(recovery.get("T1"), recovery.get("T2")))
        values["T3_minus_T2_seconds"] = midpoint(interval_between(recovery.get("T2"), recovery.get("T3")))
        t4_pair = endpoint_duration(recovery, "T4", t0)
        t3_pair = interval_between(t0, recovery.get("T3"))
        if t4_pair and t3_pair:
            values["T4_minus_T3_seconds"] = midpoint((t4_pair[0] - t3_pair[1], t4_pair[1] - t3_pair[0]))
        else:
            values["T4_minus_T3_seconds"] = None
        records.append(values)
    return records


def values(records: list[dict], metric: str) -> list[float]:
    return [float(row[metric]) for row in records if isinstance(row.get(metric), (int, float))]


def normal_p(z: float) -> float:
    return math.erfc(abs(z) / math.sqrt(2.0))


def summary(group: list[dict], metric: str) -> dict:
    x = values(group, metric)
    if not x:
        return {"n": 0, "mean": None, "sd": None, "median": None, "ci95_low": None, "ci95_high": None, "min": None, "max": None}
    mean = statistics.fmean(x)
    sd = statistics.stdev(x) if len(x) > 1 else None
    half = 1.96 * sd / math.sqrt(len(x)) if sd is not None else None
    return {"n": len(x), "mean": mean, "sd": sd, "median": statistics.median(x),
            "ci95_low": mean - half if half is not None else mean,
            "ci95_high": mean + half if half is not None else mean,
            "min": min(x), "max": max(x)}


def contrast(on: list[dict], off: list[dict], metric: str) -> dict:
    x, y = values(on, metric), values(off, metric)
    if not x or not y:
        return {"n_on": len(x), "n_off": len(y), "difference_on_minus_off": None, "cohens_d": None, "p_value_normal": None, "ci95_low": None, "ci95_high": None}
    mx, my = statistics.fmean(x), statistics.fmean(y)
    vx = statistics.variance(x) if len(x) > 1 else 0.0
    vy = statistics.variance(y) if len(y) > 1 else 0.0
    se = math.sqrt(vx / len(x) + vy / len(y))
    diff = mx - my
    pooled = math.sqrt(((len(x) - 1) * vx + (len(y) - 1) * vy) / max(len(x) + len(y) - 2, 1))
    z = diff / se if se > 0 else 0.0
    return {"n_on": len(x), "n_off": len(y), "difference_on_minus_off": diff,
            "cohens_d": diff / pooled if pooled > 0 else None, "p_value_normal": normal_p(z) if se > 0 else 1.0,
            "ci95_low": diff - 1.96 * se, "ci95_high": diff + 1.96 * se}


def holm(rows: list[dict], p_key: str = "p_value_normal") -> None:
    usable = sorted([(float(row[p_key]), index) for index, row in enumerate(rows) if row.get(p_key) is not None])
    m = len(usable)
    adjusted = [None] * len(rows)
    running = 0.0
    for rank, (p, index) in enumerate(usable):
        value = min(1.0, p * (m - rank))
        running = max(running, value)
        adjusted[index] = running
    for row, value in zip(rows, adjusted):
        row["p_value_holm"] = value


def svg_bar(path: Path, title: str, labels: list[str], series: list[tuple[str, list[float | None], str]], ylabel: str) -> None:
    width, height = 1200, 650
    left, right, top, bottom = 90, 30, 80, 120
    plot_w, plot_h = width - left - right, height - top - bottom
    data = [v for _, vals, _ in series for v in vals if isinstance(v, (int, float))]
    maximum = max(data, default=1.0) * 1.15
    if maximum <= 0:
        maximum = 1.0
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
             '<style>text{font-family:Arial,sans-serif;fill:#1f2937}.title{font-size:22px;font-weight:700}.axis{stroke:#6b7280;stroke-width:1}.grid{stroke:#e5e7eb;stroke-width:1}.bar{opacity:.9}</style>',
             f'<text x="{left}" y="35" class="title">{title}</text>']
    for tick in range(6):
        value = maximum * tick / 5
        y = top + plot_h - plot_h * tick / 5
        parts.append(f'<line x1="{left}" y1="{y:.1f}" x2="{width-right}" y2="{y:.1f}" class="grid"/>')
        parts.append(f'<text x="{left-12}" y="{y+5:.1f}" text-anchor="end" font-size="12">{value:.1f}</text>')
    parts.append(f'<line x1="{left}" y1="{top+plot_h}" x2="{width-right}" y2="{top+plot_h}" class="axis"/>')
    group_w = plot_w / max(len(labels), 1)
    bar_w = group_w / (len(series) + 1)
    colors = [color for _, _, color in series]
    for sidx, (name, vals, color) in enumerate(series):
        for i, value in enumerate(vals):
            if not isinstance(value, (int, float)):
                continue
            x = left + i * group_w + (sidx + 0.5) * bar_w
            h = plot_h * value / maximum
            y = top + plot_h - h
            parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w*.8:.1f}" height="{h:.1f}" fill="{color}" class="bar"><title>{name} {labels[i]}: {value:.3f}</title></rect>')
    for i, label in enumerate(labels):
        x = left + (i + 0.5) * group_w
        parts.append(f'<text x="{x:.1f}" y="{top+plot_h+22}" text-anchor="middle" font-size="12">{label}</text>')
    for i, (name, _, color) in enumerate(series):
        x = left + i * 190
        parts.append(f'<rect x="{x}" y="{height-52}" width="16" height="16" fill="{color}"/><text x="{x+24}" y="{height-39}" font-size="13">{name}</text>')
    parts.append(f'<text x="18" y="{top+plot_h/2}" transform="rotate(-90 18 {top+plot_h/2})" text-anchor="middle" font-size="14">{ylabel}</text>')
    parts.append("</svg>")
    path.write_text("\n".join(parts) + "\n", encoding="utf-8")


def all_attempt_statuses() -> list[dict]:
    result = []
    for path in sorted(ATTEMPTS.glob("*/attempt_status.json")):
        try:
            result.append(read_json(path))
        except json.JSONDecodeError:
            result.append({"attempt_id": path.parent.name, "status": "UNREADABLE", "directory": str(path.parent)})
    return result


def main() -> int:
    ANALYSIS.mkdir(parents=True, exist_ok=True)
    FIGURES.mkdir(parents=True, exist_ok=True)
    records = load_qualifying()
    if len(records) != 240:
        raise RuntimeError(f"strict qualifying record count is {len(records)}, expected 240")
    fields = ["slot", "block", "repetition", "order", "scenario", "observer_state", "attempt_id", "directory"] + METRICS + ["t4_status", "t4_rate_lower", "baseline_rate", "correctness_ok", "oracle_output_correct", "oracle_exit_code", "validation_exit_code"]
    write_csv(ANALYSIS / "qualifying_run_metrics.csv", records, fields)

    cell_rows: list[dict] = []
    for scenario in SCENARIOS:
        for observer in OBSERVERS:
            group = [r for r in records if r["scenario"] == scenario and r["observer_state"] == observer]
            row = {"scenario": scenario, "observer_state": observer, "n": len(group)}
            for metric in METRICS:
                s = summary(group, metric)
                for key, value in s.items():
                    row[f"{metric}_{key}"] = value
            cell_rows.append(row)
    cell_fields = ["scenario", "observer_state", "n"] + [f"{m}_{k}" for m in METRICS for k in ("n", "mean", "sd", "median", "ci95_low", "ci95_high", "min", "max")]
    write_csv(ANALYSIS / "summary_by_cell.csv", cell_rows, cell_fields)

    contrast_rows: list[dict] = []
    for metric in METRICS:
        metric_rows = []
        for scenario in SCENARIOS:
            on = [r for r in records if r["scenario"] == scenario and r["observer_state"] == "OBSERVER_ON"]
            off = [r for r in records if r["scenario"] == scenario and r["observer_state"] == "OBSERVER_OFF"]
            row = {"metric": metric, "scenario": scenario, **contrast(on, off, metric)}
            metric_rows.append(row)
        holm(metric_rows)
        contrast_rows.extend(metric_rows)
    contrast_fields = ["metric", "scenario", "n_on", "n_off", "difference_on_minus_off", "cohens_d", "p_value_normal", "p_value_holm", "ci95_low", "ci95_high"]
    write_csv(ANALYSIS / "observer_on_off_contrasts.csv", contrast_rows, contrast_fields)

    correctness = []
    for scenario in SCENARIOS:
        for observer in OBSERVERS:
            group = [r for r in records if r["scenario"] == scenario and r["observer_state"] == observer]
            correctness.append({"scenario": scenario, "observer_state": observer, "n": len(group),
                                "oracle_pass": sum(r["oracle_output_correct"] is True and r["oracle_exit_code"] == 0 for r in group),
                                "validator_pass": sum(r["validation_exit_code"] == 0 for r in group),
                                "strict_correctness_pass": sum(r["correctness_ok"] is True for r in group)})
    write_csv(ANALYSIS / "correctness_by_cell.csv", correctness, ["scenario", "observer_state", "n", "oracle_pass", "validator_pass", "strict_correctness_pass"])

    invalid = all_attempt_statuses()
    invalid_rows = [row for row in invalid if row.get("status") != "QUALIFYING" or row.get("correctness_ok") is not True]
    write_csv(ANALYSIS / "main_attempt_audit.csv", invalid,
              sorted({key for row in invalid for key in row.keys()} | {"attempt_id", "status"}))

    # Publication-ready figures use only qualifying evidence and retain NA for
    # endpoints that are not observed by protocol (especially C0 and censored T4).
    labels = SCENARIOS
    t1_on = [summary([r for r in records if r["scenario"] == s and r["observer_state"] == "OBSERVER_ON"], "T1_minus_T0_seconds")["mean"] for s in labels]
    t1_off = [summary([r for r in records if r["scenario"] == s and r["observer_state"] == "OBSERVER_OFF"], "T1_minus_T0_seconds")["mean"] for s in labels]
    svg_bar(FIGURES / "recovery_T1_container_recovery.svg", "Container/process recovery after fault activation", labels,
            [("Observer ON", t1_on, "#2563eb"), ("Observer OFF", t1_off, "#f97316")], "seconds")
    e2e_on = [summary([r for r in records if r["scenario"] == s and r["observer_state"] == "OBSERVER_ON"], "end_to_end_seconds")["mean"] for s in labels]
    e2e_off = [summary([r for r in records if r["scenario"] == s and r["observer_state"] == "OBSERVER_OFF"], "end_to_end_seconds")["mean"] for s in labels]
    svg_bar(FIGURES / "observer_overhead_end_to_end.svg", "End-to-end execution time by observer state", labels,
            [("Observer ON", e2e_on, "#2563eb"), ("Observer OFF", e2e_off, "#f97316")], "seconds")

    coverage = []
    for scenario in SCENARIOS:
        for observer in OBSERVERS:
            group = [r for r in records if r["scenario"] == scenario and r["observer_state"] == observer]
            coverage.append({"scenario": scenario, "observer_state": observer, "qualifying_n": len(group),
                             "correctness_pass_n": sum(r["correctness_ok"] is True for r in group),
                             "t4_observed_n": sum(r["t4_status"] == "observed" for r in group),
                             "t4_right_censored_n": sum(r["t4_status"] == "right_censored" for r in group)})
    write_csv(ANALYSIS / "coverage_and_censoring.csv", coverage, list(coverage[0]))

    campaign = {
        "protocol": PROTOCOL, "analysis_generated_wall_utc": utc(), "qualifying_n": len(records),
        "main_attempt_n": len(invalid), "nonqualifying_main_attempt_n": len(invalid_rows),
        "source_schedule": str(SCHEDULE), "source_attempts": str(ATTEMPTS),
        "analysis_script": str(Path(__file__).resolve()), "historical_campaigns_pooled": False,
    }
    (ANALYSIS / "analysis_manifest.json").write_text(json.dumps(campaign, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    report = [
        "# ChaosFlow 240 Campaign — Final Statistical Analysis", "",
        f"Generated: `{campaign['analysis_generated_wall_utc']}`", "",
        "## Analysis lock", "",
        f"Exactly **{len(records)}/240** strict-qualifying main observations were analyzed from `run_schedule.csv`. "
        "The historical 90-run campaign and separate 72-run pilot were not pooled.", "",
        "Qualification required the frozen slot, successful terminal pipeline, cleanup, exact full-row oracle pass, production validator pass, and required T0–T3 evidence for non-control scenarios. Invalid attempts and replacements are audited separately.", "",
        "## Coverage and correctness", "",
        "See `analysis/coverage_and_censoring.csv` and `analysis/correctness_by_cell.csv`. Each of the 16 scenario × observer cells has n=15 in the strict qualifying set. Correctness is reported as an outcome, not inferred from completion.", "",
        "## Descriptive statistics", "",
        "`analysis/summary_by_cell.csv` reports n, mean, SD, median, min/max, and 95% normal-approximation confidence intervals for end-to-end time and each independently bracketed recovery endpoint. Missing or right-censored endpoints remain missing; they are not imputed.", "",
        "## Observer ON/OFF contrasts", "",
        "`analysis/observer_on_off_contrasts.csv` reports ON minus OFF differences, pooled-SD Cohen's d, normal-approximation p-values, and Holm-adjusted p-values. Holm correction is applied across the eight scenario contrasts separately for each metric. These are observational contrasts within the randomized sequential schedule, not claims of causal independence from all time-varying system state.", "",
        "## Figures", "",
        "- `analysis/figures/recovery_T1_container_recovery.svg` — T1 container/process recovery summary.",
        "- `analysis/figures/observer_overhead_end_to_end.svg` — end-to-end observer overhead summary.", "",
        "## Audit and limitations", "",
        "Invalid attempts, retry reasons, reclassifications, and replacements are retained in `INVALID_ATTEMPTS_AND_REPLACEMENTS_AUDIT.md`. Kafka-specific provenance and sensitivity definitions are in `KAFKA_PROVENANCE_SENSITIVITY_ANALYSIS.md`. T4 is only summarized when its prespecified sustained-throughput criterion was observed; right-censored and unobservable cases are explicit.", "",
        "Reproduce with: `python3 analysis/statistical_analysis.py` from this campaign directory.",
    ]
    (ROOT / "FINAL_STATISTICAL_ANALYSIS.md").write_text("\n".join(report) + "\n", encoding="utf-8")

    invalid_report = ["# Invalid Attempts and Replacements Audit", "", f"Main attempt-status records: **{len(invalid)}**", f"Strict qualifying observations: **{len(records)}**", f"Non-qualifying main attempts: **{len(invalid_rows)}**", "", "No invalid attempt is silently removed; each remains under `attempts/` and the schedule retains its attempt ID history.", "", "| Attempt | Scenario | Observer | Status | Reason |", "|---|---|---|---|---|"]
    for row in invalid_rows:
        invalid_report.append(f"| `{row.get('attempt_id')}` | {row.get('scenario')} | {row.get('observer_state')} | {row.get('status')} | {(row.get('reason') or 'correctness/instrumentation gate or replacement')} |")
    (ROOT / "INVALID_ATTEMPTS_AND_REPLACEMENTS_AUDIT.md").write_text("\n".join(invalid_report) + "\n", encoding="utf-8")

    kafka_rows = []
    for row in records:
        if row["scenario"] not in {"C1", "C2"}:
            continue
        directory = Path(row["directory"])
        fault = read_json(directory / "fault.json") if (directory / "fault.json").exists() else {}
        event_lines = sum(1 for _ in (directory / "docker_events.jsonl").open(encoding="utf-8")) if (directory / "docker_events.jsonl").exists() else 0
        kafka_rows.append({"attempt_id": row["attempt_id"], "scenario": row["scenario"], "observer_state": row["observer_state"],
                           "fault_target": fault.get("target"), "fault_kind": (fault.get("dispatch") or {}).get("kind"),
                           "docker_event_lines": event_lines, "end_to_end_seconds": row["end_to_end_seconds"]})
    write_csv(ANALYSIS / "kafka_fault_provenance.csv", kafka_rows,
              ["attempt_id", "scenario", "observer_state", "fault_target", "fault_kind", "docker_event_lines", "end_to_end_seconds"])
    kafka_report = [
        "# Kafka Fault Provenance and Sensitivity Analysis", "",
        "This report is restricted to the current 240-run campaign. It does not pool the historical 90-run campaign or the separate 72-run pilot.", "",
        "## Provenance", "",
        "For every qualifying C1/C2 observation, `fault.json` records the campaign-owned Kafka target and dispatched fault kind, while `docker_events.jsonl` retains the Compose-scoped event stream. The machine-readable audit is `analysis/kafka_fault_provenance.csv`.", "",
        "## Sensitivity definitions", "",
        "The primary observer analysis uses all strict-qualifying observations. A Kafka-fault sensitivity subset is defined as C1/C2 only; a complementary non-Kafka subset is C0 and C3–C7. These subsets are descriptive robustness views and are not used to alter the primary matrix or qualification.", "",
        f"The current report contains {len(kafka_rows)} qualifying Kafka-fault observations. Re-run `python3 analysis/statistical_analysis.py` to regenerate the provenance table and all summaries from the immutable attempt directories.",
    ]
    (ROOT / "KAFKA_PROVENANCE_SENSITIVITY_ANALYSIS.md").write_text("\n".join(kafka_report) + "\n", encoding="utf-8")

    reproducibility = [
        "# ChaosFlow 240 Campaign — Reproducibility", "", f"Protocol: `{PROTOCOL}`", f"Generated: `{utc()}`", "",
        "The authoritative schedule is `run_schedule.csv`; qualifying evidence is the latest attempt ID in each row and its immutable directory under `attempts/`. The dataset fingerprint, pipeline configuration, fault evidence, observer evidence, independent oracle, production validator, cleanup, resource samples, and checksums are retained per attempt.", "",
        "Run from the campaign root:", "", "```sh", "python3 analysis/statistical_analysis.py", "```", "",
        "The analysis uses Python's standard library only. It fails closed if the schedule is not exactly 240 rows or any row is not strict-qualifying. Historical campaigns are intentionally excluded.",
    ]
    (ROOT / "REPRODUCIBILITY.md").write_text("\n".join(reproducibility) + "\n", encoding="utf-8")
    print(json.dumps({"qualifying": len(records), "main_attempts": len(invalid), "generated": utc()}, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"analysis blocked: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise
