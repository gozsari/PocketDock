# Contributing to PocketDock

Thanks for your interest in PocketDock! Bug reports, feature ideas, and pull requests are all welcome.

## Getting set up

The fastest way to get a working dev environment is Docker — `docker compose up --build` brings up the full stack (web, Celery worker, Redis) along with P2Rank and AutoDock Vina.

For a native install (RDKit/OpenMM via conda + external Vina/P2Rank binaries), see the [Local development section in Getting Started](https://pocketdock.readthedocs.io/en/latest/getting-started/#local-development-without-docker).

## Reporting bugs and requesting features

Open a [GitHub Issue](https://github.com/gozsari/PocketDock/issues). For bugs, please include:

- PocketDock version (commit hash or release tag)
- How you're running it (Docker / native)
- The exact input that triggered the problem (PDB + SDF if you can share them)
- The full traceback from the Celery worker logs (`docker compose logs celery`)

## Submitting a pull request

1. **Fork** the repo and create a feature branch off `main` (e.g. `fix/box-padding-edge-case`, `feat/refinement-amber99sb`).
2. **Make your change.** Keep PRs focused — one logical change per PR is much easier to review than a sweeping refactor.
3. **Add or update tests** in `docking/tests/`. The project uses pytest + pytest-django, and there's an existing fixture directory at `docking/tests/fixtures/` with small PDB/SDF inputs you can reuse.
4. **Run the test suite locally:**
   ```bash
   pytest
   ```
5. **Run the linter and formatter:**
   ```bash
   ruff check .
   ruff format .
   ```
   The CI lint workflow ([.github/workflows/lint.yml](.github/workflows/lint.yml)) enforces these on every PR.
6. **Push and open a PR** against `main`. In the description, explain *why* (the problem you're solving), not just *what* (the diff already shows that). Link related issues with `Fixes #123`.

## Code style

- Python 3.11+. Type hints are welcome but not required everywhere — focus on public APIs and tricky logic.
- Follow the existing module layout: domain logic in `docking/tasks.py` (the docking pipeline), thin views in `docking/views.py`, models in `docking/models.py`.
- `ruff` handles formatting and most lint rules — config is in `pyproject.toml`. Don't fight it.

## Adding a new dependency

- **Pure-Python / pip-installable**: add it to `requirements.txt` with a pinned upper bound.
- **Needs a system library or wheel from conda-forge** (RDKit, OpenMM, Gemmi, PDBFixer): add a `mamba install` line to the Dockerfile and the conda install command in [docs/getting-started.md](docs/getting-started.md). Also update `requirements.txt` if the package is pip-importable so editors don't flag it as missing.

## Scope of contributions

PocketDock is an *integration* of well-established tools (P2Rank, AutoDock Vina, RDKit, OpenMM). Pull requests that:

- ✅ Fix bugs in the integration layer
- ✅ Improve the UI / results presentation
- ✅ Add new scoring/refinement options that wrap an established method
- ✅ Improve docs, examples, and tests

are all welcome. Contributions that re-implement physics or scoring methods from scratch are out of scope — we prefer to call into well-validated upstream libraries.


