"""FAO-56 single-bucket root-zone water balance, simulated at daily steps.

State is S: millimetres of water stored in the root zone (theta * Zr), not a
fraction -- so rain in mm adds directly, per the spec. Each day, in order:

  1. Rain arrives minus a fixed runoff fraction (infiltration).
  2. Anything above field capacity drains out with time constant tau_d
     (tau_d -> 0 behaves like instant drainage).
  3. Plants and the atmosphere remove ETa = Ks * Kc * ET0, where Ks is 1
     while readily-available water remains and declines linearly to 0 at
     the wilting point once depletion passes RAW = p * TAW.

Simulating daily and then aggregating to weekly (done by the caller) matters
because 30mm in one day mostly runs off, while 30mm over a week mostly
infiltrates -- weekly-averaged inputs would erase that nonlinearity before it
ever reached the model.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class BucketParams:
    theta_fc: float
    theta_wp: float
    Zr: float  # mm
    Kc: float
    p: float
    tau_d: float  # days
    runoff_frac: float

    def __post_init__(self) -> None:
        if self.theta_wp >= self.theta_fc:
            raise ValueError(f"theta_wp ({self.theta_wp}) must be < theta_fc ({self.theta_fc})")

    @property
    def S_fc(self) -> float:
        """Field-capacity storage, mm."""
        return self.theta_fc * self.Zr

    @property
    def S_wp(self) -> float:
        """Wilting-point storage, mm."""
        return self.theta_wp * self.Zr

    @property
    def TAW(self) -> float:
        """Total available water, mm -- the whole budget between full and dead."""
        return self.S_fc - self.S_wp

    @property
    def RAW(self) -> float:
        """Readily available water, mm -- depletion threshold where Ks starts dropping."""
        return self.p * self.TAW


def stress_coefficient(S: np.ndarray, params: BucketParams) -> np.ndarray:
    """Ks: 1 while depletion <= RAW, then linear decline to 0 at the wilting point."""
    depletion = np.clip(params.S_fc - S, 0.0, None)
    taw, raw = params.TAW, params.RAW
    if taw <= raw:  # degenerate (p close to 1); avoid div-by-zero
        return (depletion <= raw).astype(float)
    ks = (taw - depletion) / (taw - raw)
    return np.clip(ks, 0.0, 1.0)


def simulate(
    rain_mm: np.ndarray,
    et0_mm: np.ndarray,
    params: BucketParams,
    S0: float | None = None,
) -> np.ndarray:
    """Run the daily water balance forward. Returns theta (S/Zr) for each day, same length as inputs.

    S0 defaults to field capacity (a wet start, revised away quickly by spin-up
    -- callers doing calibration should discard the first ~30 days as spin-up).
    """
    # Plain python lists in the hot loop, not numpy indexing: arr[i] on a
    # numpy array boxes a 0-d scalar on every access, which dominates the
    # cost of a loop this size (365-1000+ iterations x population x
    # generations under differential_evolution). Lists avoid that entirely.
    rain_list = rain_mm.tolist() if isinstance(rain_mm, np.ndarray) else list(rain_mm)
    et0_list = et0_mm.tolist() if isinstance(et0_mm, np.ndarray) else list(et0_mm)
    n = len(rain_list)

    S_fc = params.S_fc
    taw = params.TAW
    raw = params.RAW
    kc = params.Kc
    runoff_keep = 1.0 - params.runoff_frac
    drain_fraction = 1.0 if params.tau_d <= 1e-6 else 1.0 - np.exp(-1.0 / params.tau_d)
    taw_minus_raw = taw - raw

    s = S_fc if S0 is None else S0 * params.Zr
    s = min(max(s, 0.0), S_fc * 1.5)

    out = [0.0] * n
    for t in range(n):
        s += rain_list[t] * runoff_keep

        excess = s - S_fc
        if excess > 0:
            s -= excess * drain_fraction

        depletion = S_fc - s
        if depletion < 0.0:
            depletion = 0.0
        if taw_minus_raw <= 0:
            ks = 1.0 if depletion <= raw else 0.0
        else:
            ks = (taw - depletion) / taw_minus_raw
            if ks > 1.0:
                ks = 1.0
            elif ks < 0.0:
                ks = 0.0

        et0_t = et0_list[t]
        eta = ks * kc * (et0_t if et0_t > 0.0 else 0.0)
        s -= eta
        if s < 0.0:
            s = 0.0

        out[t] = s

    return np.asarray(out, dtype=float) / params.Zr
