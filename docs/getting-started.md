# Getting Started

This page walks you through running PocketDock locally and submitting your first docking job.

## Prerequisites

- **Docker** and **Docker Compose** (recommended) — everything is bundled in containers, including P2Rank and AutoDock Vina.
- **A protein structure** in `.pdb`, `.pdb.gz`, or `.cif` format (max 50 MB).
- **A ligand** in `.sdf`, `.mol2`, or `.mol` format (max 10 MB).

If you don't have files handy, the [RCSB PDB](https://www.rcsb.org/) is a good source for protein structures, and [PubChem](https://pubchem.ncbi.nlm.nih.gov/) provides ligands as SDF.

## Run with Docker (recommended)

```bash
git clone https://github.com/ozsari/pocketdock.git
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

Use this only if you have P2Rank and AutoDock Vina installed natively (PocketDock won't fetch them for you).

```bash
# Create and activate a virtual environment
python -m venv venv
source venv/bin/activate

# Install Python dependencies
pip install -r requirements.txt

# Apply database migrations
python manage.py migrate

# Start Redis (required for Celery)
redis-server &

# Start the Celery worker
celery -A pocketdock worker -l info &

# Run the Django dev server
python manage.py runserver
```

You'll need to set the environment variable `P2RANK_BIN` to the absolute path of your local `prank` executable. See [Configuration](configuration.md) for all environment variables.

## Next steps

- **New to docking?** Read [Concepts](concepts.md) for a quick primer on pockets, poses, and binding affinities.
- **Already comfortable with docking?** Jump to [The Results Page](user-guide/results.md) and [Interpreting Results](interpreting-results.md).
- **Want to script it?** See the [API Reference](api.md).
