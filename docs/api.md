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
| `GET` | `/api/jobs/<job_id>/results/` | Fetch full results (poses + ADMET + MM-GBSA) |
| `GET` | `/api/jobs/<job_id>/files/<path>` | Download a job artifact (PDB, PDBQT, SDF, etc.) |
| `GET` | `/api/batch/<batch_id>/` | Batch progress + per-ligand best scores |
| `GET` | `/api/ensemble/<ensemble_id>/` | Ensemble progress + consensus top-20 |
| `GET` | `/api/queue/` | Site-wide queue snapshot |
| `GET` | `/jobs/<job_id>/` | HTML status/results page (for browsers) |
| `GET` | `/batch/<batch_id>/` | HTML batch dashboard |
| `GET` | `/ensemble/<ensemble_id>/` | HTML ensemble dashboard |

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
| `num_pockets` | int | No | Default `3`, range `1`–`20` |
| `exhaustiveness` | int | No | Default `8`, range `1`–`64` |
| `scoring_function` | string | No | `vina` (default) or `vinardo` |
| `refine_poses` | bool | No | Default `false`. Run OpenMM energy minimization on each pose. |
| `rescore_mmgbsa` | bool | No | Default `false`. Compute per-pose MM-GBSA-style ΔG (kJ/mol). |
| `ensemble_method` | string | No | `none` (default), `nma`, or `md` |
| `num_conformations` | int | No | Default `5`, range `2`–`10`. Only used when `ensemble_method != none`. |

!!! note "Booleans in multipart form data"
    Form-encoded booleans accept the standard truthy strings (`true`, `on`, `1`). Omit the field for `false`.

### Response

```json
{
  "job_id": 42,
  "status": "pending"
}
```

When `ensemble_method` is `nma` or `md`, the job created here is the **ensemble parent** (`conformation_index = 0`). Children are spawned by the worker and share the same `ensemble_id`. Poll the ensemble endpoint to track them all together.

### curl example

```bash
curl -X POST http://localhost:8000/api/jobs/ \
  -F "name=EGFR + Erlotinib" \
  -F "protein_file=@1m17.pdb" \
  -F "ligand_file=@erlotinib.sdf" \
  -F "num_pockets=3" \
  -F "exhaustiveness=8" \
  -F "refine_poses=true" \
  -F "rescore_mmgbsa=true"
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
            "num_pockets": 3,
            "exhaustiveness": 8,
            "rescore_mmgbsa": "true",
        },
    )

response.raise_for_status()
job_id = response.json()["job_id"]
print(f"Submitted job {job_id}")
```

### Submitting a batch

The single-job endpoint takes one ligand file. To submit a batch programmatically, post `multipart/form-data` with `mode=batch` and one or more `ligand_files` to the same `/` view used by the form:

```bash
curl -X POST http://localhost:8000/ \
  -F "mode=batch" \
  -F "name=Kinase library" \
  -F "protein_file=@1m17.pdb" \
  -F "ligand_files=@compound_001.sdf" \
  -F "ligand_files=@compound_002.sdf" \
  -F "ligand_files=@library.sdf" \
  -F "num_pockets=3" \
  -F "exhaustiveness=8"
```

- Up to **100** ligand files per batch.
- Multi-molecule SDFs are auto-split (one job per molecule).
- The server redirects to `/batch/<batch_id>/`. Use `/api/batch/<batch_id>/` for JSON status polling. See [Batch Docking](user-guide/batch-docking.md) for the full workflow.

---

## GET /api/jobs/&lt;job_id&gt;/status/ { #get-job-status }

Poll the current state of a job.

### Response

```json
{
  "id": 42,
  "name": "EGFR + Erlotinib",
  "status": "running_vina",
  "status_display": "Running AutoDock Vina",
  "num_pockets": 3,
  "exhaustiveness": 8,
  "scoring_function": "vina",
  "error_message": "",
  "num_results": 0,
  "created_at": "2026-05-13T14:22:01Z",
  "updated_at": "2026-05-13T14:23:18Z"
}
```

If the job is still `pending`, the response also includes `queue_position` (1-indexed) and `estimated_wait_seconds`.

### Status values

| Value | Meaning |
|-------|---------|
| `pending` | Job created, not yet picked up by a worker |
| `running_ensemble` | Generating receptor conformations (NMA or MD) |
| `running_p2rank` | P2Rank pocket detection in progress |
| `running_prep` | Meeko receptor/ligand preparation in progress |
| `running_vina` | AutoDock Vina docking in progress |
| `running_refinement` | OpenMM pose minimization in progress |
| `running_mmgbsa` | MM-GBSA-style rescoring in progress |
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

Fetch all docking results for a completed job, plus the auto-computed ADMET properties.

### Response

```json
{
  "job_id": 42,
  "status": "completed",
  "complete": true,
  "protein_file": "1m17.pdb",
  "ligand_file": "erlotinib.sdf",
  "scoring_function": "Vina",
  "admet": {
    "mw": 393.44,
    "logp": 3.20,
    "hba": 6,
    "hbd": 1,
    "tpsa": 74.7,
    "rotatable_bonds": 10,
    "aromatic_rings": 3,
    "heavy_atoms": 29,
    "ring_count": 4,
    "fsp3": 0.20,
    "qed": 0.55,
    "lipinski_violations": 0,
    "lipinski_pass": true,
    "veber_pass": true
  },
  "pockets": [
    {
      "id": 101,
      "rank": 1,
      "score": 18.42,
      "probability": 0.91,
      "center_x": 12.4,
      "center_y": 3.7,
      "center_z": -8.1,
      "residue_ids": "LEU694,VAL702,...",
      "sas_points": 124,
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
      "id": 501,
      "pocket_rank": 1,
      "pocket_probability": 0.91,
      "pose_rank": 1,
      "affinity": -9.6,
      "rmsd_lb": 0.0,
      "rmsd_ub": 0.0,
      "pose_file": "results/pocket_1_pose_1.pdb",
      "combined_score": 0.672,
      "ligand_efficiency": 0.32,
      "mmgbsa_score": -142.7,
      "center_x": 12.4,
      "center_y": 3.7,
      "center_z": -8.1
    }
  ]
}
```

Notes:

- `admet` is `{}` if RDKit could not parse the ligand. Otherwise it holds the descriptors documented in [ADMET Properties](user-guide/admet.md).
- `mmgbsa_score` is `null` when `rescore_mmgbsa=false` or when rescoring failed for that pose. Units: kJ/mol, more negative = stronger binding. See [MM-GBSA Rescoring](user-guide/mmgbsa-rescoring.md) for methodology caveats.

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
print(f"  MM-GBSA ΔG: {best['mmgbsa_score']} kJ/mol")
print(f"  QED: {results['admet'].get('qed')}")
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

## GET /api/batch/&lt;batch_id&gt;/ { #get-batch-status }

Poll the progress of a batch submission. Each ligand in the batch is its own `DockingJob`; the batch endpoint aggregates them.

### Response

```json
{
  "batch_id": "a3f9c1d2e7b8",
  "total": 24,
  "completed": 18,
  "failed": 1,
  "running": 2,
  "pending": 3,
  "progress_pct": 79,
  "all_done": false,
  "jobs": [
    {
      "id": 88,
      "ligand_name": "compound_001",
      "status": "completed",
      "status_display": "Completed",
      "best_affinity": -10.3,
      "best_score": 0.812
    },
    {
      "id": 89,
      "ligand_name": "compound_002",
      "status": "running_vina",
      "status_display": "Running AutoDock Vina",
      "best_affinity": null,
      "best_score": null
    }
  ]
}
```

`best_affinity` and `best_score` summarize that ligand's best pose so far (lowest affinity / highest combined score) — `null` until the job completes at least one pose.

### Python — wait for the batch and pick the top hits

```python
import time
import requests

batch_id = "a3f9c1d2e7b8"
url = f"http://localhost:8000/api/batch/{batch_id}/"

while not requests.get(url).json()["all_done"]:
    time.sleep(15)

batch = requests.get(url).json()
ranked = sorted(
    (j for j in batch["jobs"] if j["best_score"] is not None),
    key=lambda j: j["best_score"],
    reverse=True,
)
for hit in ranked[:10]:
    print(f"{hit['ligand_name']:30s} score={hit['best_score']:.3f}  "
          f"affinity={hit['best_affinity']} kcal/mol")
```

See [Batch Docking](user-guide/batch-docking.md) for the upload-side workflow.

---

## GET /api/ensemble/&lt;ensemble_id&gt;/ { #get-ensemble-status }

Poll an ensemble run. Each conformation is a child `DockingJob` (`conformation_index` 1..N); the parent (`conformation_index = 0`) acts as the coordinator and is excluded from the children list.

### Response

```json
{
  "ensemble_id": "b81d44ae7c01",
  "total": 5,
  "completed": 4,
  "failed": 0,
  "running": 1,
  "pending": 0,
  "progress_pct": 80,
  "all_done": false,
  "conformations": [
    {
      "id": 201,
      "conformation_index": 1,
      "status": "completed",
      "status_display": "Completed",
      "best_affinity": -9.8,
      "best_score": 0.711
    }
  ],
  "best_results": [
    {
      "job_id": 201,
      "conformation": 1,
      "pocket_rank": 1,
      "pose_rank": 1,
      "affinity": -9.8,
      "combined_score": 0.711,
      "mmgbsa_score": null
    }
  ]
}
```

`best_results` is the top 20 poses across **all** conformations, sorted by `combined_score` descending — the consensus ranking. See [Ensemble Docking](user-guide/ensemble-docking.md) for methodology.

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
        data={"num_pockets": 3, "exhaustiveness": 8, "rescore_mmgbsa": "true"},
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
      f"affinity {best['affinity']} kcal/mol, score {best['combined_score']:.3f}, "
      f"MM-GBSA {best['mmgbsa_score']} kJ/mol")

# Download best pose
pose = requests.get(f"{BASE}/api/jobs/{job_id}/files/{best['pose_file']}").content
with open(f"job_{job_id}_best.pdb", "wb") as f:
    f.write(pose)
print(f"Saved best pose to job_{job_id}_best.pdb")
```

---

## Rate limits and concurrency

PocketDock has no built-in rate limiting. Concurrency is controlled by Celery — by default the worker container runs 2 worker processes (`--concurrency=2` in [docker-compose.yml](https://github.com/gozsari/PocketDock/blob/main/docker-compose.yml)). Submitting more jobs than that just queues them.

For high-throughput screening, scale the Celery worker (more replicas or higher `--concurrency`) rather than parallelizing API submissions client-side. Batch submissions count as one job per ligand for queue purposes.
