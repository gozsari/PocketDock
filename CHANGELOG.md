# Changelog

All notable changes to PocketDock are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.0.0] — 2026-05-20

First public release.

### Added

- **Pocket detection** via P2Rank 2.5 — automatic druggable-pocket prediction ranked by druggability.
- **Docking** via AutoDock Vina 1.2.7 with Meeko 0.5+ receptor/ligand preparation.
- **Single and batch docking** — submit one ligand or up to 100 in a single batch upload (auto-splits multi-molecule SDF).
- **Ensemble docking** — generate 2–10 receptor conformations via normal-mode analysis (NMA, fast) or short OpenMM molecular dynamics (thorough). Consensus top-results across conformations.
- **ADMET properties** computed for every job via RDKit: MW, logP, HBA/HBD, TPSA, QED, Lipinski and Veber rule pass/fail badges.
- **Optional OpenMM pose refinement** — AMBER14 + OBC2 implicit-solvent energy minimization of docked poses.
- **Optional MM-GBSA-style rescoring** — per-pose ΔG (kJ/mol), sortable in the results table.
- **Interaction analysis** — automatic detection of H-bonds, hydrophobic contacts, salt bridges, π-stacking, π-cation interactions, and halogen bonds.
- **Interactive 3D viewer** powered by 3Dmol.js — sortable results, 2D interaction maps, CSV / PNG export.
- **Asynchronous pipeline** — Celery + Redis with a public queue page showing position and estimated wait times.
- **REST API** for scripted access — endpoints for job submission, status polling, results, and batch/ensemble dashboards.
- **Docker Compose** stack bundling the web app, Celery worker, Redis, P2Rank 2.5, and AutoDock Vina 1.2.7 across `linux/amd64` and `linux/arm64`.
- **MkDocs documentation** site covering getting started, configuration, user guides, API reference, and troubleshooting.
- **Example dataset** in `examples/egfr_erlotinib/` — EGFR kinase domain (PDB 4HJO) plus erlotinib (PubChem CID 176870) for an end-to-end quickstart.
- **`CONTRIBUTING.md`** with contribution guidelines.
- **Ruff configuration** and `lint.yml` GitHub Actions workflow for code-style enforcement on PRs.
- **CITATION.cff** and Zenodo archival for citable releases.

### Security

- Django settings hardened for production: `DEBUG` defaults to `0`, `ALLOWED_HOSTS` defaults to `localhost,127.0.0.1`, `DJANGO_SECRET_KEY` is auto-generated in development and **required** (raises `ImproperlyConfigured`) when `DEBUG=0`.
- New `.env.example` documenting every environment variable.

### Fixed

- Missing `Platform` import in the OpenMM pose-refinement code path that would have raised `NameError` when refinement was enabled.

[Unreleased]: https://github.com/gozsari/PocketDock/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/gozsari/PocketDock/releases/tag/v1.0.0
