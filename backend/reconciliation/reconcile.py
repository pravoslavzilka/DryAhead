#!/usr/bin/env python3
"""Data-reconciliation script for the DryAhead sensor network.

Finds gaps in the 20-minute-cadence time-series readings each LoRa node should
have produced, and creates backfill instructions in Supabase's `instructions`
table for the hub to act on.

Design constraint that shapes everything here: a node only understands
``GETDATA:<since_epoch>`` and resends every locally-stored record newer than
that timestamp -- it has no way to bound the *end* of the resend. So this
script never emits one instruction per gap or per chunk; per node, it emits at
most one instruction per run, pointing at the earliest recoverable gap. See
the README for the full rationale (idempotency, retention horizon, failure
cap).

Run with --dry-run to compute and log everything without writing anything.
"""

from __future__ import annotations

import argparse
import bisect
import logging
import os
import sys
import time
from dataclasses import dataclass
from typing import Iterable

import requests

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - dotenv is a listed dependency
    load_dotenv = None


# ---------------------------------------------------------------------------
# Defaults for every tunable constant. See README.md for what each one means
# and when you'd change it.
# ---------------------------------------------------------------------------
DEFAULT_NODE_IDS = [1, 2, 3, 4, 5]
DEFAULT_CADENCE_MINUTES = 20
DEFAULT_LOOKBACK_DAYS = 35
DEFAULT_NODE_RETENTION_DAYS = 14
DEFAULT_FAILURE_CAP = 3
DEFAULT_HTTP_TIMEOUT_SECONDS = 15.0
DEFAULT_PAGE_SIZE = 1000

# A reading counts as satisfying an expected slot if it falls within half a
# cadence interval of it either way -- absorbs node clock jitter without
# needing readings to land on exact epoch multiples.
TOLERANCE_FRACTION_OF_CADENCE = 0.5

# Don't flag the most recent expected slot(s) as missing just because the
# node hasn't had time to report yet. One full cadence interval of grace.
GRACE_PERIODS_OF_CADENCE = 1

IN_FLIGHT_STATES = ("Posted", "Received")
FAILED_STATE = "Failed to resolve"

logger = logging.getLogger("reconcile")


class ReconciliationError(RuntimeError):
    """Raised for conditions that should abort the run with a non-zero exit."""


@dataclass
class Config:
    supabase_url: str
    supabase_key: str
    node_ids: list[int]
    cadence_minutes: int
    lookback_days: int
    retention_days: int
    failure_cap: int
    http_timeout: float
    dry_run: bool

    @property
    def cadence_seconds(self) -> int:
        return self.cadence_minutes * 60

    @property
    def tolerance_seconds(self) -> int:
        return int(self.cadence_seconds * TOLERANCE_FRACTION_OF_CADENCE)

    @property
    def grace_seconds(self) -> int:
        return self.cadence_seconds * GRACE_PERIODS_OF_CADENCE

    @property
    def lookback_seconds(self) -> int:
        return self.lookback_days * 86400

    @property
    def retention_seconds(self) -> int:
        return self.retention_days * 86400


@dataclass
class NodeOutcome:
    node_id: int
    gaps_found: int
    action: str  # "created" | "skipped" | "none"
    reason: str
    range_start: int | None = None


def load_config(argv: list[str] | None = None) -> Config:
    """Read env vars and CLI flags into a validated Config.

    Raises ReconciliationError for missing/invalid required environment
    variables so main() can fail fast with a helpful message.
    """
    if load_dotenv is not None:
        load_dotenv()

    parser = argparse.ArgumentParser(
        description="Find gaps in sensor readings and queue GETDATA backfill instructions."
    )
    parser.add_argument(
        "--nodes",
        default=",".join(str(n) for n in DEFAULT_NODE_IDS),
        help=f"Comma-separated node IDs to check (default: {DEFAULT_NODE_IDS}).",
    )
    parser.add_argument(
        "--cadence-minutes",
        type=int,
        default=DEFAULT_CADENCE_MINUTES,
        help="Expected minutes between readings per node (default: %(default)s).",
    )
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=DEFAULT_LOOKBACK_DAYS,
        help="How far back to scan for gaps, in days (default: %(default)s).",
    )
    parser.add_argument(
        "--retention-days",
        type=int,
        default=DEFAULT_NODE_RETENTION_DAYS,
        help=(
            "Node local-storage horizon in days; gaps older than this are "
            "presumed overwritten on the node and are not requested (default: %(default)s)."
        ),
    )
    parser.add_argument(
        "--failure-cap",
        type=int,
        default=DEFAULT_FAILURE_CAP,
        help=(
            "Stop retrying a node once it has this many 'Failed to resolve' "
            "instructions covering the same-or-earlier range_start (default: %(default)s)."
        ),
    )
    parser.add_argument(
        "--http-timeout",
        type=float,
        default=DEFAULT_HTTP_TIMEOUT_SECONDS,
        help="HTTP timeout in seconds for each Supabase request (default: %(default)s).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute and log everything; create no instructions.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity (default: %(default)s).",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    supabase_url = os.environ.get("SUPABASE_URL", "").strip()
    supabase_key = os.environ.get("SUPABASE_KEY", "").strip()
    missing = [
        name
        for name, value in [("SUPABASE_URL", supabase_url), ("SUPABASE_KEY", supabase_key)]
        if not value
    ]
    if missing:
        raise ReconciliationError(
            "Missing required environment variable(s): "
            f"{', '.join(missing)}. Copy .env.example to .env and fill them in, "
            "or export them before running."
        )

    try:
        node_ids = [int(n.strip()) for n in args.nodes.split(",") if n.strip()]
    except ValueError as exc:
        raise ReconciliationError(f"--nodes must be a comma-separated list of integers: {exc}")
    if not node_ids:
        raise ReconciliationError("--nodes resolved to an empty list of node IDs.")

    if args.cadence_minutes <= 0:
        raise ReconciliationError("--cadence-minutes must be positive.")
    if args.lookback_days <= 0:
        raise ReconciliationError("--lookback-days must be positive.")
    if args.retention_days <= 0:
        raise ReconciliationError("--retention-days must be positive.")
    if args.failure_cap <= 0:
        raise ReconciliationError("--failure-cap must be positive.")

    return Config(
        supabase_url=supabase_url.rstrip("/"),
        supabase_key=supabase_key,
        node_ids=node_ids,
        cadence_minutes=args.cadence_minutes,
        lookback_days=args.lookback_days,
        retention_days=args.retention_days,
        failure_cap=args.failure_cap,
        http_timeout=args.http_timeout,
        dry_run=args.dry_run,
    )


class SupabaseClient:
    """Thin PostgREST client scoped to exactly what this script needs.

    Uses the anon key only: `select` on `readings`, `select`+`insert` on
    `instructions`. Never touches the service_role key. See README for the
    expected RLS policies.
    """

    def __init__(self, base_url: str, api_key: str, timeout: float):
        self._base_url = base_url
        self._timeout = timeout
        self._session = requests.Session()
        self._session.headers.update(
            {
                "apikey": api_key,
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
        )

    def check_connectivity(self) -> None:
        """Fail fast with a clear message on auth/network problems."""
        url = f"{self._base_url}/rest/v1/instructions"
        try:
            resp = self._session.get(
                url, params={"select": "id", "limit": 1}, timeout=self._timeout
            )
        except requests.exceptions.RequestException as exc:
            raise ReconciliationError(f"Could not reach Supabase at {self._base_url}: {exc}")

        if resp.status_code in (401, 403):
            raise ReconciliationError(
                f"Supabase rejected the request (HTTP {resp.status_code}). Check "
                "SUPABASE_KEY is a valid anon key and that RLS policies grant it "
                "select on `instructions`."
            )
        if resp.status_code >= 400:
            raise ReconciliationError(
                f"Supabase connectivity check failed: HTTP {resp.status_code}: {resp.text[:300]}"
            )

    def get_reading_timestamps(self, node_id: int, start: int, end: int) -> set[int]:
        """All recorded_at values for a node within [start, end], paginated."""
        timestamps: set[int] = set()
        offset = 0
        while True:
            params = {
                "select": "recorded_at",
                "node_id": f"eq.{node_id}",
                "recorded_at": [f"gte.{start}", f"lte.{end}"],
                "order": "recorded_at.asc",
                "limit": DEFAULT_PAGE_SIZE,
                "offset": offset,
            }
            rows = self._get(f"{self._base_url}/rest/v1/readings", params)
            if not rows:
                break
            timestamps.update(int(row["recorded_at"]) for row in rows)
            if len(rows) < DEFAULT_PAGE_SIZE:
                break
            offset += DEFAULT_PAGE_SIZE
        return timestamps

    def get_in_flight_min_range_start(self, node_id: int) -> int | None:
        """Smallest range_start among this node's Posted/Received instructions."""
        params = {
            "select": "range_start",
            "node_id": f"eq.{node_id}",
            "state": f"in.({','.join(IN_FLIGHT_STATES)})",
            "order": "range_start.asc",
            "limit": 1,
        }
        rows = self._get(f"{self._base_url}/rest/v1/instructions", params)
        if not rows:
            return None
        return int(rows[0]["range_start"])

    def count_failed_at_or_before(self, node_id: int, range_start: int) -> int:
        """How many Failed-to-resolve instructions already cover this range_start or earlier."""
        params = {
            "select": "id",
            "node_id": f"eq.{node_id}",
            "state": f"eq.{FAILED_STATE}",
            "range_start": f"lte.{range_start}",
        }
        rows = self._get(f"{self._base_url}/rest/v1/instructions", params)
        return len(rows)

    def create_instruction(self, node_id: int, range_start: int) -> None:
        body = {
            "node_id": node_id,
            "command": "GETDATA",
            "range_start": range_start,
            "range_end": None,
            "state": "Posted",
        }
        url = f"{self._base_url}/rest/v1/instructions"
        try:
            resp = self._session.post(
                url,
                json=body,
                headers={"Prefer": "return=minimal"},
                timeout=self._timeout,
            )
        except requests.exceptions.RequestException as exc:
            raise ReconciliationError(f"Failed to create instruction for node {node_id}: {exc}")
        if resp.status_code not in (200, 201, 204):
            raise ReconciliationError(
                f"Supabase rejected instruction insert for node {node_id}: "
                f"HTTP {resp.status_code}: {resp.text[:300]}"
            )

    def _get(self, url: str, params: dict) -> list[dict]:
        try:
            resp = self._session.get(url, params=params, timeout=self._timeout)
        except requests.exceptions.RequestException as exc:
            raise ReconciliationError(f"Request to {url} failed: {exc}")
        if resp.status_code >= 400:
            raise ReconciliationError(
                f"Supabase returned HTTP {resp.status_code} for {url}: {resp.text[:300]}"
            )
        try:
            return resp.json()
        except ValueError as exc:
            raise ReconciliationError(f"Non-JSON response from {url}: {exc}")


def expected_timestamps(window_start: int, window_end: int, cadence_seconds: int) -> list[int]:
    """Every epoch second that is a multiple of cadence_seconds within [window_start, window_end].

    Anchored to epoch zero (not to "now") so the expected grid is stable
    across runs regardless of when the script happens to execute.
    """
    if window_end < window_start:
        return []
    first = -(-window_start // cadence_seconds) * cadence_seconds  # ceil division
    return list(range(first, window_end + 1, cadence_seconds))


def find_missing(
    expected: Iterable[int], actual: set[int], tolerance_seconds: int
) -> list[int]:
    """Expected slots with no actual reading within tolerance_seconds of them."""
    if not actual:
        return list(expected)
    sorted_actual = sorted(actual)
    missing = []
    for slot in expected:
        lo = slot - tolerance_seconds
        hi = slot + tolerance_seconds
        if not _has_value_in_range(sorted_actual, lo, hi):
            missing.append(slot)
    return missing


def _has_value_in_range(sorted_values: list[int], lo: int, hi: int) -> bool:
    i = bisect.bisect_left(sorted_values, lo)
    return i < len(sorted_values) and sorted_values[i] <= hi


def reconcile_node(client: SupabaseClient, config: Config, node_id: int, now: int) -> NodeOutcome:
    window_start = now - config.lookback_seconds
    window_end = now - config.grace_seconds

    actual = client.get_reading_timestamps(node_id, window_start, window_end)
    expected = expected_timestamps(window_start, window_end, config.cadence_seconds)
    missing = find_missing(expected, actual, config.tolerance_seconds)

    if not missing:
        logger.info("node=%d gaps=0 action=none reason=no_gaps", node_id)
        return NodeOutcome(node_id, 0, "none", "no_gaps")

    earliest_gap = min(missing)
    horizon_cutoff = now - config.retention_seconds

    if earliest_gap < horizon_cutoff:
        recoverable = [t for t in missing if t >= horizon_cutoff]
        if not recoverable:
            logger.warning(
                "node=%d gaps=%d action=none reason=trimmed_to_horizon_no_recoverable "
                "earliest_gap=%d horizon_cutoff=%d note='all missing data predates the "
                "node retention horizon and is presumed permanently lost'",
                node_id,
                len(missing),
                earliest_gap,
                horizon_cutoff,
            )
            return NodeOutcome(node_id, len(missing), "none", "trimmed_to_horizon_no_recoverable")
        range_start = horizon_cutoff
        logger.warning(
            "node=%d gaps=%d earliest_gap=%d trimmed_range_start=%d "
            "note='data between earliest_gap and horizon_cutoff is presumed permanently lost'",
            node_id,
            len(missing),
            earliest_gap,
            range_start,
        )
    else:
        range_start = earliest_gap

    in_flight_start = client.get_in_flight_min_range_start(node_id)
    if in_flight_start is not None and in_flight_start <= range_start:
        logger.info(
            "node=%d gaps=%d action=skipped reason=already_in_flight "
            "candidate_range_start=%d existing_range_start=%d",
            node_id,
            len(missing),
            range_start,
            in_flight_start,
        )
        return NodeOutcome(node_id, len(missing), "skipped", "already_in_flight", range_start)

    failed_count = client.count_failed_at_or_before(node_id, range_start)
    if failed_count >= config.failure_cap:
        logger.warning(
            "node=%d gaps=%d action=skipped reason=capped_unrecoverable "
            "candidate_range_start=%d failed_count=%d failure_cap=%d "
            "note='node presumed dead or offline with nothing new to backfill'",
            node_id,
            len(missing),
            range_start,
            failed_count,
            config.failure_cap,
        )
        return NodeOutcome(node_id, len(missing), "skipped", "capped_unrecoverable", range_start)

    if config.dry_run:
        logger.info(
            "node=%d gaps=%d action=would_create range_start=%d (dry-run, no write performed)",
            node_id,
            len(missing),
            range_start,
        )
        return NodeOutcome(node_id, len(missing), "would_create", "dry_run", range_start)

    client.create_instruction(node_id, range_start)
    logger.info(
        "node=%d gaps=%d action=created range_start=%d",
        node_id,
        len(missing),
        range_start,
    )
    return NodeOutcome(node_id, len(missing), "created", "ok", range_start)


def main(argv: list[str] | None = None) -> int:
    try:
        config = load_config(argv)
    except ReconciliationError as exc:
        # logging isn't configured yet if this fails before basicConfig ran
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    logger.info(
        "starting reconciliation nodes=%s cadence_min=%d lookback_days=%d "
        "retention_days=%d failure_cap=%d dry_run=%s",
        config.node_ids,
        config.cadence_minutes,
        config.lookback_days,
        config.retention_days,
        config.failure_cap,
        config.dry_run,
    )

    client = SupabaseClient(config.supabase_url, config.supabase_key, config.http_timeout)

    try:
        client.check_connectivity()
    except ReconciliationError as exc:
        logger.error(str(exc))
        return 1

    now = int(time.time())
    outcomes: list[NodeOutcome] = []
    try:
        for node_id in config.node_ids:
            outcomes.append(reconcile_node(client, config, node_id, now))
    except ReconciliationError as exc:
        logger.error("aborting: %s", exc)
        return 1

    created = sum(1 for o in outcomes if o.action in ("created", "would_create"))
    skipped = sum(1 for o in outcomes if o.action == "skipped")
    none_needed = sum(1 for o in outcomes if o.action == "none")
    logger.info(
        "run summary: nodes=%d instructions_created=%d skipped=%d no_action=%d",
        len(outcomes),
        created,
        skipped,
        none_needed,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
