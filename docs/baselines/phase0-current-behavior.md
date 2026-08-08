# Phase 0 Current-Behavior Baseline

Captured: 2026-08-08 on macOS Apple Silicon.

## What is verified

- The clean `acoustics-phase0` environment matches the pinned direct dependency versions in `environment-phase0-osx-arm64.yml` on `osx-arm64`.
- The existing 8 m × 6 m × 3.5 m box calculation reproduces 30 stored modal frequencies and its current statistical room metrics within stated tolerances.
- The CLI processes a watertight cube and writes JSON/CSV output.
- The independent rigid-box helper enumerates all 89 closed-form modes in 20–150 Hz; the current solver's failure to match the complete set is retained as a known defect.
- `acoustic_analysis.py` and every Python source under `src/` match upstream revision `7b114b738ed4cfd68738be20700dd2b1ce3e0564` byte-for-byte and are checked by `phase0-production-source.sha256`.

## Confirmed known defects

- Arbitrary imported geometry is replaced with its axis-aligned bounding box.
- `--repair` raises a `TypeError` because the CLI passes an unsupported keyword.
- `--freq-range` targets the midpoint and does not enumerate the complete interval.
- `--resolution` is parsed but does not change the FEM mesh.

Each item is represented by a causal strict expected-failure test under `tests/known_defects`; only its named current-defect exception may produce XFAIL.

## Reproducibility evidence

- Manifest: `environment-phase0-osx-arm64.yml`
- Manifest SHA256: `5b23eb636c86993252fde31e9d340e10a01e3881bf689962fefbd588258e47f7`
- Scope: pinned direct dependencies only; this is not a transitive lock.
- Production-source reference: `https://github.com/anatrini/AcousticFEM` at revision `7b114b738ed4cfd68738be20700dd2b1ce3e0564`
- Upstream archive SHA256: `4a798932decc7b8de6c87c5497ecf919ec78d5a7f25be178d86d90b822e07a4a`

## Reproduction

```bash
bash scripts/verify_phase0.sh
```

Expected result: normal tests have zero skips/failures/errors; exactly four known-defect tests are collected and reported as XFAIL with zero ordinary skips/failures/errors; source hashes match; the command exits 0.

## Engineering status

This baseline proves repeatability of the current software behavior only. It does not validate complex geometry, the complex Helmholtz forced response, frequency-dependent complex impedance models, absolute SPL, subwoofer frequency response, convergence, project calibration, standards compliance, or production readiness.

The following pre-existing limitations are deferred non-Phase-0 blockers:

- Fixed-cell receiver evaluation is replaced in Phase 2 by geometric point location and validated spatial evaluation.
- The existing materials YAML is not connected to the solver; it is replaced by the evidence-graded impedance contract and solver integration in Phase 3.
- ParaView/VTKHDF output behavior and the user documentation disagree; artifact behavior and reporting are unified in Phase 4.
