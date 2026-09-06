"""Site constants, node scope, and Supabase credential loading.

Independent of ml/option_one/config.py -- written from scratch, but the
site coordinates and credential-fallback pattern come from reading (not
importing) ml/option_one/config.py and ml/option_one/data_supabase.py.
"""
from __future__ import annotations

import os
from pathlib import Path

# Same physical site as option_one/option_two (Zajezova, Slovensko) --
# see ml/option_one/config.py and frontend/src/hooks/useLocalWeather.js.
LAT = 48.453782
LON = 19.216477

# Scope -- firm, per task spec: nodes 1, 4, 5 only (not option_one's full
# NODE_IDS = [1, 2, 3, 4, 5]).
NODE_IDS = [1, 4, 5]

# ESP32 nodes call analogReadResolution(12) in firmware/nodes/*/*.ino
# (both node_with_rtc and node_no_rtc) -- raw is a 12-bit ADC count,
# physically bounded to this range regardless of what the soil is doing.
ADC_MIN = 0
ADC_MAX = 4095

# Per contracts/telemetry.md's stated cadence and option_one's config.py --
# nodes report roughly every 20 minutes.
READING_CADENCE_MINUTES = 20

THIS_DIR = Path(__file__).resolve().parent          # .../ml/option_three/configs
OPTION_THREE_DIR = THIS_DIR.parent                  # .../ml/option_three
REPO_ROOT = THIS_DIR.parents[2]                     # .../DryAhead


class SupabaseError(RuntimeError):
    pass


def load_credentials(env_path: str | Path | None = None) -> tuple[str, str]:
    """SUPABASE_URL/SUPABASE_KEY from ml/option_three/.env if present,
    else frontend/.env's VITE_SUPABASE_URL/VITE_SUPABASE_ANON_KEY -- same
    Supabase project, same read-only anon key (select-only via RLS on
    `readings` and `sensor_calibration`). Mirrors the fallback pattern in
    ml/option_one/data_supabase.py's load_credentials(), reimplemented
    here rather than imported, per the "no imports from option_one" rule.

    Never write a literal credential value to any tracked file -- this
    function only reads from .env files (themselves git-ignored) or the
    process environment.
    """
    try:
        from dotenv import load_dotenv

        load_dotenv(env_path or (OPTION_THREE_DIR / ".env"))
    except ImportError:
        pass

    url = os.environ.get("SUPABASE_URL", "").strip()
    key = os.environ.get("SUPABASE_KEY", "").strip()
    if url and key:
        return url.rstrip("/"), key

    fallback = REPO_ROOT / "frontend" / ".env"
    if fallback.exists():
        env: dict[str, str] = {}
        for line in fallback.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
        url = env.get("VITE_SUPABASE_URL", "")
        key = env.get("VITE_SUPABASE_ANON_KEY", "")
        if url and key:
            return url.rstrip("/"), key

    raise SupabaseError(
        "No Supabase credentials found. Copy ml/option_three/.env.example to "
        "ml/option_three/.env and fill it in (same project as frontend/.env)."
    )
