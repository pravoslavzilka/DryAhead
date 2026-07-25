# 1. Use a monorepo for the drought-platform project

Date: 2026-07-25

## Status

Accepted

## Context

The drought-platform project spans six distinct domains: hardware circuit design, mechanical
enclosure design, firmware, ML, backend, and frontend. These domains are built with different
toolchains (KiCad/CAD, PlatformIO/C++, Python, Python, Python, TypeScript) and could reasonably
live in separate repositories.

However, several parts of the system have a tight, byte-level coupling — most importantly, the
LoRa telemetry packet layout (`contracts/telemetry.md`) that firmware produces and backend
consumes. Early on, a single person or small team is likely to be working across multiple domains
in the same sitting (e.g. changing a sensor's telemetry field and updating both firmware and
backend to match).

## Decision

We will use a single monorepo containing all six domains plus the shared `contracts/` folder,
rather than six separate repositories.

## Consequences

- Cross-domain changes (e.g. adding a telemetry field) can be made and reviewed as one change,
  instead of coordinated across repos.
- `contracts/` can sit at the top level as a shared dependency, with no need for a package
  registry or git submodules to share it between firmware and backend.
- CI must use path filters (see `.github/workflows/`) so that, e.g., a firmware-only change
  doesn't trigger frontend tests — otherwise CI time grows with unrelated work.
- Hardware design binaries (KiCad, CAD) are tracked with git-lfs within the same repo, so the
  repo needs git-lfs set up even for contributors who never touch hardware files.
- If a domain's tooling or release cadence diverges significantly in the future (e.g. hardware
  design wants its own versioned releases), we may need to reconsider splitting it out.
