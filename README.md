# PocketDock - Automated Molecular Docking Pipeline

A web-based tool that integrates **P2Rank** for binding pocket prediction and **AutoDock Vina** for molecular docking, with interactive **3Dmol.js** visualization.

**Documentation**: <https://ozsari.github.io/pocketdock/>

## Features

- Upload protein (PDB/CIF) and compound (SDF/MOL2) files
- Automatic pocket detection using P2Rank v2.5
- Grid box calculation from predicted pocket geometry
- Molecular docking with AutoDock Vina v1.2.7
- Combined scoring: pocket probability + binding affinity
- Interactive 3D visualization with 3Dmol.js
- Sortable results table with CSV export

## Quick Start (Docker)

```bash
docker compose up --build
```

The application will be available at **http://localhost:8000**.

## Architecture

| Service | Description |
|---------|-------------|
| **web** | Django app serving the UI and API |
| **celery** | Celery worker running docking pipeline tasks |
| **redis** | Message broker for Celery |

## Pipeline

1. **P2Rank** detects binding pockets in the uploaded protein structure
2. **Meeko** prepares receptor and ligand PDBQT files for docking
3. **AutoDock Vina** docks the ligand into each selected pocket
4. Results are ranked by a combined score of pocket probability and binding affinity

## Configuration

Environment variables (set in `docker-compose.yml`):

| Variable | Default | Description |
|----------|---------|-------------|
| `VINA_EXHAUSTIVENESS` | 8 | Vina search exhaustiveness |
| `VINA_NUM_MODES` | 9 | Max number of docking poses |
| `VINA_BOX_PADDING` | 5.0 | Padding around pocket (Angstroms) |
| `VINA_DEFAULT_BOX_SIZE` | 20.0 | Default grid box size |

## Tech Stack

- **Backend**: Django 5.x, Django REST Framework, Celery
- **Tools**: P2Rank 2.5, AutoDock Vina 1.2.7, Meeko
- **Frontend**: Django Templates, Tailwind CSS, 3Dmol.js
- **Infrastructure**: Docker Compose, Redis

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Upload page |
| POST | `/api/jobs/` | Create docking job |
| GET | `/api/jobs/<id>/status/` | Poll job status |
| GET | `/api/jobs/<id>/results/` | Get results data |
| GET | `/api/jobs/<id>/files/<path>` | Serve molecular files |
| GET | `/jobs/<id>/` | Job status/results page |

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

Note: Local development requires P2Rank and AutoDock Vina to be installed separately.
