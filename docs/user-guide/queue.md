# Queue

The **`/queue/`** page shows the current state of the docking queue across the whole server. Use it to see how busy PocketDock is before submitting a new job, or to track how your job is moving up the line.

## What's on the page

Three sections, each auto-refreshed every 5 seconds:

1. **Summary tiles** at the top — three numbers:
    - `In queue` — jobs waiting to start.
    - `Running now` — jobs currently being processed by a worker.
    - `Done today` — completed jobs in the last 24 hours.
2. **Running now** — jobs in any of the running stages (`running_p2rank`, `running_prep`, `running_vina`), with a live "running for X" timestamp.
3. **Waiting** — pending jobs in submission order. Each shows its position in the queue (`#1`, `#2`, …).
4. **Recently finished** — the last 50 jobs that finished in the last 24 hours, with their total duration.

## Why names are redacted

Every row shows `Job #<id>` rather than the user-supplied job name or uploaded filenames. PocketDock's job URLs are public by default (anyone with the URL can see the results), so the queue page deliberately doesn't make it *easier* to discover what other people are docking. If you have your own job's URL — `/jobs/<id>/` — you'll still see your own name and filenames there.

## Estimated wait time

When your own job is pending, its [status page](monitoring.md) shows two numbers:

- **Queue position** — how many jobs are ahead of yours.
- **Estimated wait** — when your job will start running (not when it'll finish).

The estimate is calculated as:

$$
\text{wait seconds} \approx \frac{(\text{jobs running} + \text{jobs queued ahead of you}) \times \text{avg duration}}{\text{worker concurrency}}
$$

Where:

- **avg duration** is the rolling average wall-clock of the last 20 completed jobs (defaults to 4 minutes when no history exists).
- **worker concurrency** is the number of Celery worker processes — set via the `WORKER_CONCURRENCY` env var; should match `--concurrency=N` in `docker-compose.yml`.

### Why the estimate may be off

The formula assumes all jobs take the same time and that running jobs just started. Reality is messier:

- A job that's been running for 4 minutes will probably finish soon, but the formula still budgets a full average duration for it.
- A job with `exhaustiveness=32` takes ~4× longer than the default; the average doesn't know about per-job parameters.
- P2Rank crashes that fail-fast pull the average down; large flexible ligands push it up.

Treat the ETA as a rough order-of-magnitude — useful for "should I wait or come back later" but not precise.

## API

The same data is available as JSON at **`GET /api/queue/`**:

```bash
curl http://localhost:8000/api/queue/
```

Response shape:

```json
{
  "pending_count": 3,
  "running_count": 2,
  "completed_today_count": 47,
  "worker_concurrency": 2,
  "avg_duration_seconds": 251,
  "running": [
    { "id": 142, "status": "running_vina", "status_display": "Running AutoDock Vina",
      "created_at": "2026-05-14T10:12:01Z", "updated_at": "2026-05-14T10:14:33Z" }
  ],
  "pending": [
    { "id": 143, "status": "pending", "status_display": "Pending",
      "created_at": "2026-05-14T10:14:00Z", "updated_at": "2026-05-14T10:14:00Z",
      "queue_position": 1 }
  ],
  "recent": [
    { "id": 141, "status": "completed", "status_display": "Completed",
      "created_at": "2026-05-14T10:08:01Z", "updated_at": "2026-05-14T10:11:42Z",
      "duration_seconds": 221 }
  ]
}
```

The same redaction applies — no `name`, no `protein_file`, no `ligand_file`.

## Worker concurrency

PocketDock's Celery worker runs at `--concurrency=2` by default ([docker-compose.yml](https://github.com/gozsari/PocketDock/blob/main/docker-compose.yml)), meaning two jobs can run in parallel. To match the queue page's ETA calculation:

| Setting | Where | Default |
|---------|-------|---------|
| Celery process count | `--concurrency=N` in `docker-compose.yml` | `2` |
| ETA assumption | `WORKER_CONCURRENCY` env var | `2` |

If you change one, change the other — otherwise the ETA on the queue page will be systematically wrong.
