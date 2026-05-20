# Getting Started

This page walks you through running PocketDock locally and submitting your first docking job.

## Prerequisites

- **Docker** and **Docker Compose** (recommended) — everything is bundled in containers, including P2Rank and AutoDock Vina.
- **A protein structure** in `.pdb`, `.pdb.gz`, or `.cif` format (max 50 MB).
- **A ligand** in `.sdf`, `.mol2`, or `.mol` format (max 10 MB).

If you don't have files handy, the [RCSB PDB](https://www.rcsb.org/) is a good source for protein structures, and [PubChem](https://pubchem.ncbi.nlm.nih.gov/) provides ligands as SDF.

## Run with Docker (recommended)

```bash
git clone https://github.com/gozsari/PocketDock.git
cd pocketdock
docker compose up --build
```

The first build takes ~5–10 minutes because it downloads P2Rank v2.5 and the AutoDock Vina v1.2.7 binary. Subsequent runs start in seconds.

When the logs settle, open [http://localhost:8000](http://localhost:8000).

!!! tip "What got started"
    `docker compose up` brings up three containers:

    - **web** — Django app on port 8000
    - **celery** — worker that runs the docking pipeline
    - **redis** — message broker between web and worker

## Run from the published image

If you don't need to modify the code, you can run PocketDock straight from the multi-arch image published to GitHub Container Registry — no clone required.

Create an empty directory, save the snippet below as `docker-compose.yml`, then run `docker compose up`:

```yaml
services:
  redis:
    image: redis:7-alpine
    volumes:
      - redis_data:/data

  web:
    image: ghcr.io/gozsari/pocketdock:latest
    command: >
      sh -c "python manage.py migrate --noinput &&
             gunicorn pocketdock.wsgi:application --bind 0.0.0.0:8000 --workers 3 --timeout 300"
    ports:
      - "8000:8000"
    volumes:
      - ./media:/app/media
      - db_data:/app/data
      - static_files:/app/staticfiles
    environment:
      - DJANGO_SETTINGS_MODULE=pocketdock.settings
      - CELERY_BROKER_URL=redis://redis:6379/0
      - CELERY_RESULT_BACKEND=redis://redis:6379/0
      - DEBUG=${DEBUG:-1}
    depends_on:
      - redis

  celery:
    image: ghcr.io/gozsari/pocketdock:latest
    command: >
      sh -c "sleep 5 && celery -A pocketdock worker -l info --concurrency=2"
    volumes:
      - ./media:/app/media
      - db_data:/app/data
    environment:
      - DJANGO_SETTINGS_MODULE=pocketdock.settings
      - CELERY_BROKER_URL=redis://redis:6379/0
      - CELERY_RESULT_BACKEND=redis://redis:6379/0
      - DEBUG=${DEBUG:-1}
    depends_on:
      - redis
      - web

volumes:
  redis_data:
  static_files:
  db_data:
```

Open [http://localhost:8000](http://localhost:8000) once the logs settle. Uploaded structures land in `./media/` next to your `docker-compose.yml` so you can inspect them on the host.

### Image tags

`:latest` follows the most recent published build; tagged releases are available as `:vX.Y.Z`. Browse the full tag list at the [GitHub Container Registry package page](https://github.com/gozsari/PocketDock/pkgs/container/pocketdock). Pinning to a release tag is recommended for anything beyond a quick try.

!!! warning "Production deployments"
    The snippet above runs with `DEBUG=1` so it works out of the box. Before exposing PocketDock to anyone else, create a `.env` file alongside `docker-compose.yml` with `DEBUG=0` and a long, random `DJANGO_SECRET_KEY`, and add `env_file: [.env]` to the `web` and `celery` services.

## Your first job

1. Open the app and you'll land on the **upload page**.
2. (Optional) Give the job a name like `EGFR + Erlotinib`.
3. Drag your **protein file** into the left drop zone.
4. Drag your **ligand file** into the right drop zone.
5. Open the **Advanced Settings** panel if you want to change defaults:
      - **Number of pockets to dock** — default `3`. PocketDock will dock against the top-3 P2Rank pockets.
      - **Vina exhaustiveness** — default `8`. Increase for more thorough conformational search at the cost of runtime.
6. Click **Run Docking**.

You'll be redirected to the **status page**, which auto-refreshes every 5 seconds and shows a 4-step pipeline indicator:

1. Pocket detection (P2Rank)
2. Structure preparation (Meeko)
3. AutoDock Vina docking
4. Results ready

When the job finishes, the status page automatically redirects to the **results page**. A typical job takes 2–10 minutes depending on protein size and exhaustiveness.

## What you'll see in the results

- **3D viewer** on the left with the protein, the docked ligand pose, and color-coded interaction lines
- **Results table** on the right with one row per pose — sort by affinity, pocket probability, or combined score
- **Pose info panel** with binding affinity, ligand efficiency, and an estimated dissociation constant (Kd)
- **2D Interaction Map** and **Interaction Details** tabs for closer analysis

See [The Results Page](user-guide/results.md) for the full tour.

## Local development (without Docker)

This route is more work — Docker is strongly recommended unless you have a specific reason to install everything by hand. PocketDock relies on several scientific libraries (RDKit, OpenMM, PDBFixer, Gemmi) and two external binaries (P2Rank, AutoDock Vina) that are *not* installable via `pip` alone.

### 1. Create a conda/mamba environment with the scientific stack

[Mamba](https://github.com/mamba-org/mamba) or [Conda](https://docs.conda.io/) is required — these libraries are not on PyPI in a usable form.

```bash
mamba create -n pocketdock python=3.11 -c conda-forge
mamba activate pocketdock
mamba install -c conda-forge rdkit openmm pdbfixer gemmi
```

### 2. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 3. Install the external docking binaries

PocketDock does not bundle these — install them yourself and either put them on `PATH` or set the matching environment variable.

| Binary | Version | Download | Env var |
|---|---|---|---|
| **P2Rank** | 2.5 | <https://github.com/rdk/p2rank/releases/tag/2.5> | `P2RANK_BIN=/path/to/prank` |
| **AutoDock Vina** | 1.2.7 | <https://github.com/ccsb-scripps/AutoDock-Vina/releases/tag/v1.2.7> | Must be on `PATH` as `vina` |

### 4. Start Redis, the worker, and the web server

```bash
# Apply database migrations
python manage.py migrate

# Start Redis (required for Celery)
redis-server &

# Start the Celery worker
celery -A pocketdock worker -l info &

# Run the Django dev server
python manage.py runserver
```

See [Configuration](configuration.md) for the full list of environment variables.

## Next steps

- **New to docking?** Read [Concepts](concepts.md) for a quick primer on pockets, poses, and binding affinities.
- **Already comfortable with docking?** Jump to [The Results Page](user-guide/results.md) and [Interpreting Results](interpreting-results.md).
- **Want to script it?** See the [API Reference](api.md).
