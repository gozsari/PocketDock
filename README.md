# PocketDock — Automated Molecular Docking Pipeline

A web-based platform that predicts druggable binding pockets with **P2Rank**, docks single ligands or whole libraries with **AutoDock Vina**, generates flexible-receptor ensembles via **NMA** or short **OpenMM MD**, computes **ADMET** properties with RDKit, optionally refines poses with OpenMM, and rescores with an approximate **MM-GBSA** method — all visualized in your browser with **3Dmol.js**.

**Documentation**: <https://pocketdock.readthedocs.io/>

## Features

- **Pocket detection** — automatic druggable-pocket prediction with P2Rank v2.5
- **Single and batch docking** — submit one ligand or up to 100 in a single batch
- **Ensemble docking** — generate 2–10 receptor conformations via NMA (fast) or OpenMM MD (thorough)
- **ADMET properties** — RDKit-computed MW, logP, HBA/HBD, TPSA, QED, Lipinski & Veber pass/fail (every job)
- **Pose refinement** *(optional)* — OpenMM AMBER14 + OBC2 implicit-solvent energy minimization
- **MM-GBSA-style rescoring** *(optional)* — per-pose ΔG (kJ/mol), sortable in the results table
- **Interaction analysis** — H-bonds, hydrophobic, salt bridges, π-stacking, π-cation, halogen bonds
- **Interactive 3D viewer** — 3Dmol.js with sortable results, 2D interaction maps, CSV / PNG export
- **REST API + Celery queue** — script everything from Python or curl

## Quick Start (Docker)

```bash
docker compose up --build
```

The application will be available at **<http://localhost:8000>**. See the [Getting Started guide](https://pocketdock.readthedocs.io/en/latest/getting-started/) for prerequisites and first-run walkthrough.

## Architecture

| Service | Description |
|---------|-------------|
| **web** | Django app serving the UI and REST API |
| **celery** | Celery worker running the docking pipeline |
| **redis** | Message broker and result backend |

## Pipeline

1. *(Optional)* **Ensemble** — generate N receptor conformations with NMA or short OpenMM MD
2. **P2Rank** detects binding pockets and ranks them by druggability
3. **Meeko** prepares receptor and ligand PDBQT files
4. **RDKit** computes ADMET descriptors from the ligand
5. **AutoDock Vina** docks the ligand into the top *N* pockets
6. **Interaction analysis** annotates each pose with detected contacts
7. *(Optional)* **OpenMM refinement** energy-minimizes each pose
8. *(Optional)* **MM-GBSA rescoring** computes a per-pose ΔG

Results are ranked by a combined score of pocket probability and binding affinity. See [Interpreting Results](https://pocketdock.readthedocs.io/en/latest/interpreting-results/) for the full scoring details.

## Configuration

Environment variables (set in `docker-compose.yml`):

| Variable | Default | Description |
|----------|---------|-------------|
| `VINA_EXHAUSTIVENESS` | `8` | Vina search exhaustiveness |
| `VINA_NUM_MODES` | `9` | Max number of docking poses per pocket |
| `VINA_BOX_PADDING` | `5.0` | Padding around the pocket (Å) |
| `VINA_DEFAULT_BOX_SIZE` | `20.0` | Fallback grid-box edge length (Å) |
| `WORKER_CONCURRENCY` | `2` | Celery worker processes |

Full reference: [Configuration](https://pocketdock.readthedocs.io/en/latest/configuration/).

## Tech Stack

- **Backend** — Django 5.x, Django REST Framework, Celery 5.4+
- **Docking** — P2Rank 2.5, AutoDock Vina 1.2.7, Meeko 0.5+
- **Cheminformatics** — RDKit (ADMET, ligand parsing)
- **Structural mechanics** — OpenMM + PDBFixer (ensemble MD, pose refinement); Gemmi (structure I/O)
- **Frontend** — Django templates, Tailwind CSS, 3Dmol.js
- **Infrastructure** — Docker Compose, Redis 5.0+, Gunicorn

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Upload page (single + batch tabs) |
| POST | `/api/jobs/` | Create a docking job |
| GET | `/api/jobs/<id>/status/` | Poll job status |
| GET | `/api/jobs/<id>/results/` | Get results (poses, ADMET, MM-GBSA) |
| GET | `/api/jobs/<id>/files/<path>` | Serve molecular files |
| GET | `/api/batch/<batch_id>/` | Batch progress + per-ligand best scores |
| GET | `/api/ensemble/<ensemble_id>/` | Ensemble progress + consensus top-20 |
| GET | `/jobs/<id>/` | Job status / results page |
| GET | `/batch/<batch_id>/` | Batch dashboard page |
| GET | `/ensemble/<ensemble_id>/` | Ensemble dashboard page |

Full reference with request/response schemas: [API Reference](https://pocketdock.readthedocs.io/en/latest/api/).

## Local Development

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install Python dependencies
pip install -r requirements.txt

# Run migrations
python manage.py migrate

# Start Redis (requires local Redis)
redis-server &

# Start Celery worker
celery -A pocketdock worker -l info &

# Run development server
python manage.py runserver
```

Note: Local development requires P2Rank and AutoDock Vina to be installed separately. OpenMM and RDKit are pulled in via `requirements.txt`.

## Citation

If you use PocketDock in your research, please cite it using the metadata in [`CITATION.cff`](CITATION.cff) (v2.0.0, released 2026-05-17).

## Acknowledgements

PocketDock was conceived and designed by **Gökhan Özsarı** (Chalmers University of Technology). Development was assisted by [Claude](https://www.anthropic.com/claude) (Anthropic) as an AI coding aid.
