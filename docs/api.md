# API Reference

PocketDock exposes a small REST API for submitting jobs, polling status, and retrieving results programmatically. Use it to integrate docking into a screening pipeline, run batch jobs, or build a custom UI.

## Conventions

- **Base URL**: `http://<host>:8000` (replace with your deployment URL).
- **Auth**: None. All endpoints are public — protect with a reverse proxy if needed.
- **Content type**: JSON for status/results endpoints; `multipart/form-data` for job submission; raw file content for the file-serving endpoint.
- **Errors**: Non-2xx HTTP status with a JSON body `{"error": "..."}`.

## Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/api/jobs/` | Submit a new docking job |
| `GET` | `/api/jobs/<job_id>/status/` | Poll job status |
| `GET` | `/api/jobs/<job_id>/results/` | Fetch full results |
| `GET` | `/api/jobs/<job_id>/files/<path>` | Download a job artifact (PDB, PDBQT, SDF, etc.) |
| `GET` | `/jobs/<job_id>/` | HTML status/results page (for browsers) |

---

## POST /api/jobs/

Create a new docking job. Same handler as the upload form.

### Request

`multipart/form-data` with these fields:

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `name` | string | No | Free-text job label |
| `protein_file` | file | Yes | `.pdb`, `.pdb.gz`, or `.cif` (≤ 50 MB) |
| `ligand_file` | file | Yes | `.sdf`, `.mol2`, or `.mol` (≤ 10 MB) |
| `n_pockets` | int | No | Default `3`, range `1`–`20` |
| `exhaustiveness` | int | No | Default `8`, range `1`–`64` |

### Response

```json
{
  "job_id": 42,
  "status": "pending"
}
```

### curl example

```bash
curl -X POST http://localhost:8000/api/jobs/ \
  -F "name=EGFR + Erlotinib" \
  -F "protein_file=@1m17.pdb" \
  -F "ligand_file=@erlotinib.sdf" \
  -F "n_pockets=3" \
  -F "exhaustiveness=8"
```

### Python example

```python
import requests

with open("1m17.pdb", "rb") as p, open("erlotinib.sdf", "rb") as l:
    response = requests.post(
        "http://localhost:8000/api/jobs/",
        files={
            "protein_file": p,
            "ligand_file": l,
        },
        data={
            "name": "EGFR + Erlotinib",
            "n_pockets": 3,
            "exhaustiveness": 8,
        },
    )

response.raise_for_status()
job_id = response.json()["job_id"]
print(f"Submitted job {job_id}")
```

---

## GET /api/jobs/&lt;job_id&gt;/status/ { #get-job-status }

Poll the current state of a job.

### Response

```json
{
  "job_id": 42,
  "status": "running_vina",
  "name": "EGFR + Erlotinib",
  "protein_file": "1m17.pdb",
  "ligand_file": "erlotinib.sdf",
  "error_message": null,
  "created_at": "2026-05-13T14:22:01Z"
}
```

### Status values

| Value | Meaning |
|-------|---------|
| `pending` | Job created, not yet picked up by a worker |
| `running_p2rank` | P2Rank pocket detection in progress |
| `running_prep` | Meeko receptor/ligand preparation in progress |
| `running_vina` | AutoDock Vina docking in progress |
| `completed` | Done — results available |
| `failed` | Pipeline failed; see `error_message` (truncated to 2000 chars) |

### Polling pattern (Python)

```python
import time
import requests

job_id = 42
url = f"http://localhost:8000/api/jobs/{job_id}/status/"

while True:
    status = requests.get(url).json()
    print(status["status"])
    if status["status"] == "completed":
        break
    if status["status"] == "failed":
        raise RuntimeError(status["error_message"])
    time.sleep(5)

print("Done!")
```

---

## GET /api/jobs/&lt;job_id&gt;/results/

Fetch all docking results for a completed job.

### Response

```json
{
  "job_id": 42,
  "status": "completed",
  "protein_file": "1m17.pdb",
  "ligand_file": "erlotinib.sdf",
  "pockets": [
    {
      "rank": 1,
      "score": 18.42,
      "probability": 0.91,
      "center_x": 12.4,
      "center_y": 3.7,
      "center_z": -8.1,
      "residue_ids": ["LEU694", "VAL702", "..."],
      "composition": {
        "hydrophobic": 0.45,
        "polar": 0.30,
        "positive": 0.10,
        "negative": 0.10,
        "special": 0.05
      }
    }
  ],
  "results": [
    {
      "pocket_rank": 1,
      "pocket_probability": 0.91,
      "pose_rank": 1,
      "affinity": -9.6,
      "rmsd_lb": 0.0,
      "rmsd_ub": 0.0,
      "pose_file": "results/pocket_1_pose_1.pdb",
      "combined_score": 0.672,
      "ligand_efficiency": 0.32
    }
  ]
}
```

### curl example

```bash
curl http://localhost:8000/api/jobs/42/results/ | jq .
```

### Python example — find the best pose

```python
import requests

results = requests.get("http://localhost:8000/api/jobs/42/results/").json()
best = max(results["results"], key=lambda r: r["combined_score"])

print(f"Best pose: pocket {best['pocket_rank']}, pose {best['pose_rank']}")
print(f"  Affinity: {best['affinity']} kcal/mol")
print(f"  Combined score: {best['combined_score']:.3f}")
print(f"  Pose file: {best['pose_file']}")
```

---

## GET /api/jobs/&lt;job_id&gt;/files/&lt;path&gt;

Serve a file from the job's working directory. Used by the 3D viewer to load poses, but you can use it to download artifacts directly.

### Common paths

| Path | Contents |
|------|----------|
| `<protein_filename>` | The uploaded protein file |
| `<ligand_filename>` | The uploaded ligand file |
| `receptor.pdbqt` | Vina-ready prepared receptor |
| `ligand.pdbqt` | Vina-ready prepared ligand |
| `p2rank_output/<protein>_predictions.csv` | Raw P2Rank predictions |
| `results/pocket_<R>_pose_<P>.pdb` | A single docked pose as PDB |
| `results/pocket_<R>_pose_<P>_interactions.json` | Detected interactions for that pose |

### curl example

```bash
# Download the best pose found above
curl -o best_pose.pdb \
  "http://localhost:8000/api/jobs/42/files/results/pocket_1_pose_1.pdb"
```

---

## End-to-end example: submit, wait, fetch best pose

```python
import time
import requests

BASE = "http://localhost:8000"

# Submit
with open("1m17.pdb", "rb") as p, open("erlotinib.sdf", "rb") as l:
    job = requests.post(
        f"{BASE}/api/jobs/",
        files={"protein_file": p, "ligand_file": l},
        data={"n_pockets": 3, "exhaustiveness": 8},
    ).json()

job_id = job["job_id"]
print(f"Submitted job {job_id}")

# Wait
status_url = f"{BASE}/api/jobs/{job_id}/status/"
while (status := requests.get(status_url).json())["status"] not in ("completed", "failed"):
    print(f"  ...{status['status']}")
    time.sleep(5)

if status["status"] == "failed":
    raise RuntimeError(status["error_message"])

# Fetch results
results = requests.get(f"{BASE}/api/jobs/{job_id}/results/").json()
best = max(results["results"], key=lambda r: r["combined_score"])
print(f"Best: pocket {best['pocket_rank']} pose {best['pose_rank']}, "
      f"affinity {best['affinity']} kcal/mol, score {best['combined_score']:.3f}")

# Download best pose
pose = requests.get(f"{BASE}/api/jobs/{job_id}/files/{best['pose_file']}").content
with open(f"job_{job_id}_best.pdb", "wb") as f:
    f.write(pose)
print(f"Saved best pose to job_{job_id}_best.pdb")
```

---

## Rate limits and concurrency

PocketDock has no built-in rate limiting. Concurrency is controlled by Celery — by default the worker container runs 2 worker processes (`--concurrency=2` in [docker-compose.yml](https://github.com/gozsari/PocketDock/blob/main/docker-compose.yml)). Submitting more jobs than that just queues them.

For high-throughput screening, scale the Celery worker (more replicas or higher `--concurrency`) rather than parallelizing API submissions client-side.
