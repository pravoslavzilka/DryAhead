"""Orchestrates the full option_three pipeline for nodes 1, 4, 5:

  1. Supabase access check + fetch readings/calibration (data/loaders.py)
  2. Clean each node's readings (data/clean.py), write reports + plots
  3. Fetch Open-Meteo hourly weather, extract drying windows (events/windows.py)
  4. Compute sub-daily ET0 (weather/subdaily.py)
  5. Calibrate each node jointly across its windows (model/calibrate.py)
  6. Validate: equifinality, hold-out, persistence, stage check (eval/validate.py)
  7. Write configs/nodes/node_{id}.json and reports/node_{id}.md

NOT RUN THIS SESSION -- no code-execution tooling was available (see
NIGHT_SUMMARY.md and NIGHT_BLOCKED.md at the top of ml/option_three/).
Written and reasoned through carefully, but unverified end-to-end. Run it
with `python -m ml.option_three.run_pipeline` from the repo root once
ml/option_three/.env (or frontend/.env) has real Supabase credentials.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pandas as pd

from .configs import site
from .data import loaders, clean
from .events import windows as win
from .weather import subdaily
from .model.calibrate import WindowData, calibrate_node
from .model.drydown import precompute_et0_intervals
from .eval import validate


def build_window_data(readings: pd.DataFrame, windows: list[win.Window], hourly_et0: pd.Series) -> list[WindowData]:
    out = []
    for w in windows:
        mask = (readings["ts"] >= w.start) & (readings["ts"] <= w.end)
        wr = readings.loc[mask].sort_values("ts")
        times = pd.DatetimeIndex(wr["ts"])
        out.append(
            WindowData(
                times=times,
                observed=wr["raw"].to_numpy(dtype=float),
                hourly_et0=hourly_et0,
                et0_intervals=precompute_et0_intervals(times, hourly_et0),
            )
        )
    return out


def run_node(node_id: int, all_readings: pd.DataFrame, url: str, key: str) -> dict:
    node_readings_raw = all_readings[all_readings["node_id"] == node_id]

    weather = loaders.fetch_hourly_weather(
        site.LAT, site.LON,
        start_date=node_readings_raw["ts"].min().date().isoformat(),
        end_date=node_readings_raw["ts"].max().date().isoformat(),
    )
    hourly_precip = pd.Series(
        weather["hourly"]["precipitation"].to_numpy(dtype=float),
        index=pd.DatetimeIndex(weather["hourly"]["time"]),
    )
    et0_series, et0_method = subdaily.hourly_et0(weather)
    print(f"node {node_id}: ET0 method = {et0_method}")

    cleaned = clean.clean_node(node_readings_raw, hourly_precip)
    clean.plot_cleaning(node_readings_raw, cleaned["flags"], node_id, site.OPTION_THREE_DIR / "reports" / f"node_{node_id}_cleaning.png")

    rain_events = win.find_rain_events(hourly_precip)
    sign = win.detect_sign_convention(cleaned["clean"], rain_events)
    kept, all_windows, no_response = win.find_windows(node_id, cleaned["clean"], rain_events, sign)

    result = {
        "node_id": node_id,
        "sign_convention": sign,
        "et0_method": et0_method,
        "cleaning_report": cleaned["report"],
        "n_windows_detected": len(all_windows),
        "n_windows_kept": len(kept),
        "n_rain_events_no_response": len(no_response),
    }

    if len(kept) < 3:
        result["calibrated"] = False
        result["reason"] = f"only {len(kept)} usable window(s) (need >= 3) -- see task spec, not a bug to work around"
        return result

    window_data = build_window_data(cleaned["clean"], kept, et0_series)
    fit = calibrate_node(window_data, seed=0)
    equifinality = validate.equifinality(window_data, n_seeds=12)
    persistence = validate.persistence_benchmark(window_data)
    stage = validate.stage_check(window_data)
    holdout = validate.holdout_validate(window_data, holdout_index=0)

    result.update(
        {
            "calibrated": True,
            "params": fit["params"],
            "kge": fit["kge"],
            "equifinality": {k: v for k, v in equifinality["per_param"].items()},
            "persistence": persistence,
            "holdout": holdout,
            "stage_check_flat_windows": sum(1 for s in stage if s["flat"]),
        }
    )

    node_config = {
        "node_id": node_id,
        "fit_date": datetime.now(timezone.utc).isoformat(),
        "params": fit["params"],
        "kge": fit["kge"],
        "n_windows": len(kept),
        "equifinality_cv": {k: v["cv"] for k, v in equifinality["per_param"].items()},
    }
    out_path = site.OPTION_THREE_DIR / "configs" / "nodes" / f"node_{node_id}.json"
    out_path.write_text(json.dumps(node_config, indent=2), encoding="utf-8")

    return result


def _commit_node(node_id: int) -> None:
    """Commit whatever this node produced under ml/option_three/, so a
    kill/timeout partway through the full run (each node is ~80-90 min of
    real compute) only loses the node in progress, not everything already
    finished. Best-effort: prints and continues on failure rather than
    crashing the run over a git problem."""
    import subprocess

    try:
        subprocess.run(["git", "add", "ml/option_three"], cwd=site.REPO_ROOT, check=True)
        subprocess.run(
            ["git", "commit", "-m", f"option_three: node {node_id} calibration run"],
            cwd=site.REPO_ROOT,
            check=True,
        )
    except subprocess.CalledProcessError as e:
        print(f"  (commit for node {node_id} skipped/failed: {e})")


def main():
    url, key = site.load_credentials()
    loaders.check_access(url, key)

    raw = loaders.fetch_readings_raw(url, key, site.NODE_IDS)
    prepared = clean.prepare_readings(raw, site.NODE_IDS)

    summary_path = site.OPTION_THREE_DIR / "reports" / "run_summary.json"
    results = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else {}

    for node_id in site.NODE_IDS:
        config_path = site.OPTION_THREE_DIR / "configs" / "nodes" / f"node_{node_id}.json"
        if str(node_id) in results or config_path.exists():
            print(f"=== node {node_id}: already done, skipping (resumable run) ===")
            continue
        print(f"=== node {node_id} ===")
        results[str(node_id)] = run_node(node_id, prepared, url, key)
        summary_path.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
        print(f"wrote {summary_path} (through node {node_id})")
        _commit_node(node_id)

    print("all nodes done")


if __name__ == "__main__":
    main()
