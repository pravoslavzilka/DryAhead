#!/usr/bin/env python3
"""Raw ADC -> % water content from the 2026-11-22 bench run.   PROVISIONAL - see DISCLAIMER.

    python vwc_convert.py <bench_csv> <sensor_calibration_raw.json> <readings_raw.json> <out_dir> <theta_water_pct>

Anchors (bench numbers only; the stored node values are used ONLY for 'water'):
    0 %            = bench oven-dry soil reading (per bench sensor; mean of the 3 for nodes)
    theta_water %  = the stored node 'water' reading (50 or 100 are the options discussed)
    in between     = saturating curve fitted to the bench levels 0-26.5 %, interpolated beyond
Model:  g(theta) = (1-exp(-theta/tau)) / (1-exp(-theta_water/tau))     0..1
        raw      = r_dry - (r_dry - r_water) * g(theta)
        theta    = -tau * ln(1 - g * (1-exp(-theta_water/tau)))
"""
import csv, json, sys, collections, pathlib
import numpy as np
from scipy.optimize import least_squares

BENCH, CAL, READ, OUT = (pathlib.Path(a) for a in sys.argv[1:5])
THETA_W = float(sys.argv[5]) if len(sys.argv) > 5 else 50.0
TAG = f"water{THETA_W:.0f}"
OUT.mkdir(parents=True, exist_ok=True)
V_ML, FLOOR, SENSORS = 800.0, 20.0, (1, 2, 3)

DISCLAIMER = ("PROVISIONAL: one oven-dry soil, 3 bench sensors, one run, room temperature. Measured 0-26.5 % VWC "
              "(0-11 % +/-1 pt, 11-17 % +/-2-4, 17-26.5 % indicative +/-5-10). Above 26.5 % the curve is INTERPOLATED to the "
              f"'water' reading, assumed = {THETA_W:.0f} %, and is not validated. 0 % = bench oven-dry reading applied to nodes "
              "although bench sensors and nodes are different units (offset unverified). Not a certified measurement.")

cells = collections.defaultdict(list)
for r in csv.DictReader(open(BENCH)):
    cells[(int(r["sensor"]), 100 * float(r["water_ml"]) / V_ML)].append(float(r["mean_raw"]))
R0 = {s: float(np.mean(cells[(s, 0.0)])) for s in SENSORS}
R_DRY_NODES = float(np.mean(list(R0.values())))
cal = {n["node_id"]: n for n in json.load(open(CAL))}
R_WATER = float(np.mean([n["water"] for n in cal.values()]))
SPAN = {s: R0[s] - R_WATER for s in SENSORS}


def cell_sd(s, t):
    v = cells[(s, t)]
    if len(v) > 1:
        return float(np.std(v, ddof=1))
    o = [np.std(cells[(x, t)], ddof=1) for x in SENSORS if x != s and len(cells.get((x, t), [])) > 1]
    return float(np.mean(o)) if o else 100.0


def rows(excl=None):
    return [(s, t, float(np.mean(v)), float(np.hypot(FLOOR, cell_sd(s, t) / np.sqrt(len(v)))))
            for (s, t), v in sorted(cells.items()) if (s, t) != excl]


def g_of(t, tau, tw=None):
    tw = THETA_W if tw is None else tw
    return (1 - np.exp(-t / tau)) / (1 - np.exp(-tw / tau))


def fit_tau(excl=None, tw=None):
    rr = rows(excl)
    T = np.array([r[1] for r in rr]); Y = np.array([r[2] for r in rr]); W = np.array([r[3] for r in rr])
    Rd = np.array([R0[r[0]] for r in rr]); Sp = np.array([SPAN[r[0]] for r in rr])
    res = least_squares(lambda x: (Rd - Sp * g_of(T, x[0], tw) - Y) / W, [15.0], bounds=(1, 800))
    return float(res.x[0]), 2 * res.cost / (len(Y) - 1)


TAU, CHI2 = fit_tau()
print(f"[water={THETA_W:.0f}%] bench dry (0%) = {np.round([R0[s] for s in SENSORS])}  water reading used = {R_WATER:.0f}  "
      f"tau={TAU:.2f}  chi2/dof={CHI2:.2f}")


def to_vwc(raw, r_dry, r_water, tau=None, tw=None):
    tau = TAU if tau is None else tau
    tw = THETA_W if tw is None else tw
    g = np.clip((r_dry - np.asarray(raw, float)) / (r_dry - r_water), 0, 1)
    return -tau * np.log(1 - g * (1 - np.exp(-tw / tau)))


def reliability(th):
    return np.select([th <= 11, th <= 17, th <= 26.5, th < THETA_W - 0.05], ["A", "B", "C", "D"], "S")


est = collections.defaultdict(list)
for (s, t), v in sorted(cells.items()):
    raw = float(np.mean(v))
    est["M1 straight line dry->water"].append((t, THETA_W * (R0[s] - raw) / SPAN[s]))
    tau_cv, _ = fit_tau(excl=(s, t))
    est["M2 saturating curve (leave-one-out)"].append((t, float(to_vwc(raw, R0[s], R_WATER, tau_cv))))
    pts = [(tt, np.mean(vv)) for (ss, tt), vv in cells.items() if ss == s and tt <= 11.01 and (ss, tt) != (s, t)]
    c = np.polyfit([p[0] for p in pts], [p[1] for p in pts], 1)
    est["M3 line fitted on 0-11 %, extrapolated"].append((t, (raw - c[1]) / c[0]))
print("  method                                  band       n    bias    RMSE   (points of % water content)")
lines = ["method,band,n,bias_pts,rmse_pts"]
for m, v in est.items():
    a = np.array(v)
    for lo, hi in ((-1, 11.01), (11.01, 17.01), (17.01, 27)):
        sel = (a[:, 0] > lo) & (a[:, 0] <= hi)
        if sel.sum():
            e = a[sel, 1] - a[sel, 0]
            band = f"{max(lo, 0):.0f}-{min(hi, 26.5):.1f}"
            lines.append(f"{m},{band},{sel.sum()},{e.mean():+.2f},{np.sqrt(np.mean(e ** 2)):.2f}")
            print(f"  {m:38s} {band:>9s}  {sel.sum():3d}  {e.mean():+6.2f}  {np.sqrt(np.mean(e ** 2)):6.2f}")
open(OUT / f"vwc_method_comparison_{TAG}.csv", "w").write("\n".join(lines) + "\n")

grid = [t for t in (0, 2, 4, 6, 8, 11, 14, 17, 20, 23, 26.5, 30, 35, 40, 45, 50, 60, 70, 80, 90, 100) if t <= THETA_W]
tbl = ["theta_pct,g,reliability"] + [f"{t},{float(g_of(t, TAU)):.3f},{reliability(np.array(t))}" for t in grid]
open(OUT / f"vwc_lookup_{TAG}.csv", "w").write("\n".join(tbl) + "\n")
json.dump({"theta_water_pct": THETA_W, "tau": TAU, "chi2_dof": CHI2, "r_dry_bench_per_sensor": R0,
           "r_dry_used_for_nodes": R_DRY_NODES, "r_water_mean_for_bench_side": R_WATER,
           "formula": "g=(r_dry-raw)/(r_dry-r_water); theta=-tau*ln(1-g*(1-exp(-theta_water/tau)))",
           "disclaimer": DISCLAIMER}, open(OUT / f"vwc_model_{TAG}.json", "w"), indent=2)

per = collections.defaultdict(list)
for x in json.load(open(READ)):
    if x["node_id"] in cal and x["raw"] is not None and 500 <= x["raw"] <= 4000:
        per[x["node_id"]].append(x["raw"])
print(f"  nodes (0% = mean bench dry {R_DRY_NODES:.0f}; span end = each node's own 'water'):")
out = ["node,n,pct_readings_at_or_above_bench_dry,p5,median,p95,pct_A,pct_B,pct_C,pct_D,pct_S"]
nv = {}
for n in sorted(per):
    arr = np.array(per[n])
    th = to_vwc(arr, R_DRY_NODES, cal[n]["water"])
    nv[n] = th
    cls = reliability(th)
    sh = {k: 100 * np.mean(cls == k) for k in "ABCDS"}
    clip = 100 * np.mean(arr >= R_DRY_NODES)
    out.append(f"{n},{len(arr)},{clip:.0f},{np.percentile(th, 5):.1f},{np.median(th):.1f},{np.percentile(th, 95):.1f},"
               + ",".join(f"{sh[k]:.0f}" for k in "ABCDS"))
    print(f"    node {n}: n={len(arr):5d} raw median {np.median(arr):5.0f} | readings >= bench dry (->0%): {clip:3.0f}% | "
          f"p5/med/p95 {np.percentile(th, 5):4.1f}/{np.median(th):4.1f}/{np.percentile(th, 95):4.1f} | "
          f"A{sh['A']:3.0f} B{sh['B']:3.0f} C{sh['C']:3.0f} D{sh['D']:3.0f} S{sh['S']:3.0f} %")
open(OUT / f"vwc_node_summary_{TAG}.csv", "w").write("\n".join(out) + "\n")

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

fig, ax = plt.subplots(1, 2, figsize=(13, 4.8))
cols = ["#c2561b", "#1b6ec2", "#2e8b57"]
for (m, v), c in zip(est.items(), cols):
    a = np.array(v)
    ax[0].scatter(a[:, 0], a[:, 1], s=16, color=c, alpha=.7, label=m)
ax[0].plot([0, 30], [0, 30], "k--", lw=1)
ax[0].set_ylim(-2, min(THETA_W, 80) + 2)
ax[0].set_xlabel("true water content, % (water ml / 800 ml)")
ax[0].set_ylabel("estimated, %")
ax[0].set_title("Bench run: estimate vs truth")
ax[0].legend(fontsize=7, loc="upper left")
ax[1].boxplot([nv[n] for n in sorted(nv)], tick_labels=[f"node {n}" for n in sorted(nv)], showfliers=False)
ax[1].set_ylabel("converted %")
ax[1].set_title(f"Node history converted (water reading = {THETA_W:.0f} %)")
fig.text(0.5, 0.005, "PROVISIONAL - one soil, 3 bench sensors; >26.5 % interpolated to an assumed water anchor",
         ha="center", fontsize=8)
fig.tight_layout(rect=(0, 0.03, 1, 1))
fig.savefig(OUT / f"vwc_conversion_{TAG}.png", dpi=140)
print("  DISCLAIMER:", DISCLAIMER[:90], "...")
