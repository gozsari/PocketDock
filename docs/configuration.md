# Configuration

All runtime configuration is via environment variables. Set them in `docker-compose.yml`, your shell, or whatever orchestration layer you're using.

## Environment variables

### Django

| Variable | Default | Description |
|----------|---------|-------------|
| `DJANGO_SECRET_KEY` | `django-insecure-pocketdock-dev-key-change-in-production` | Django's cryptographic signing key. **Override in any non-trivial deployment.** |
| `DEBUG` | `1` | `1` enables Django debug mode (verbose errors). Set to `0` for production. |
| `ALLOWED_HOSTS` | `*` | Comma-separated list of hostnames Django will serve. Tighten in production. |

### Celery / Redis

| Variable | Default | Description |
|----------|---------|-------------|
| `CELERY_BROKER_URL` | `redis://localhost:6379/0` | Redis URL for the Celery broker |
| `CELERY_RESULT_BACKEND` | `redis://localhost:6379/0` | Redis URL for Celery task results |
| `WORKER_CONCURRENCY` | `2` | Number of parallel Celery worker processes — used by the [Queue](user-guide/queue.md) page to compute ETA. **Must match `--concurrency=N` in the celery service's command in `docker-compose.yml`**, otherwise the ETA will be systematically wrong. |

In the bundled [docker-compose.yml](https://github.com/ozsari/pocketdock/blob/main/docker-compose.yml), both default to `redis://redis:6379/0` (the in-network Redis service).

### P2Rank

| Variable | Default | Description |
|----------|---------|-------------|
| `P2RANK_BIN` | `/opt/p2rank/prank` | Absolute path to the P2Rank `prank` executable |

In the Docker image P2Rank is installed at the default path. For local development, set this to wherever you installed P2Rank.

### AutoDock Vina defaults

These set the docking parameter defaults used when the user doesn't override them via the upload form.

| Variable | Default | Description |
|----------|---------|-------------|
| `VINA_EXHAUSTIVENESS` | `8` | Default search exhaustiveness |
| `VINA_NUM_MODES` | `9` | Maximum number of poses returned per pocket |
| `VINA_BOX_PADDING` | `5.0` | Padding (Å) added to the pocket bounding box |
| `VINA_DEFAULT_BOX_SIZE` | `20.0` | Fallback box edge length (Å) when pocket geometry can't be inferred |

The docking box is computed as `pocket_extent + 2 × VINA_BOX_PADDING` along each axis, with a floor of `VINA_DEFAULT_BOX_SIZE`. Larger boxes search more space but slow Vina down disproportionately.

## File-upload limits

Hard-coded in [pocketdock/settings.py](https://github.com/ozsari/pocketdock/blob/main/pocketdock/settings.py):

```python
DATA_UPLOAD_MAX_MEMORY_SIZE = 50 * 1024 * 1024  # 50 MB
FILE_UPLOAD_MAX_MEMORY_SIZE = 50 * 1024 * 1024  # 50 MB
```

The upload form layers form-level validation on top:

- **Protein**: ≤ 50 MB
- **Ligand**: ≤ 10 MB

Raise these by editing `settings.py` and the validators in [docking/forms.py](https://github.com/ozsari/pocketdock/blob/main/docking/forms.py) — no env var.

## Celery task time limit

```python
CELERY_TASK_TIME_LIMIT = 3600  # 1 hour
```

A docking task that runs longer than this is killed. Crank it up if you're docking large flexible ligands at high exhaustiveness against big proteins. There's no env var override; edit `settings.py` directly.

## Production hardening checklist

If you're deploying PocketDock to anything beyond your laptop, change the following:

- [ ] Set a real `DJANGO_SECRET_KEY` (e.g., `python -c "import secrets; print(secrets.token_urlsafe(50))"`).
- [ ] Set `DEBUG=0`.
- [ ] Restrict `ALLOWED_HOSTS` to your actual hostnames.
- [ ] Put PocketDock behind a reverse proxy (nginx, Caddy, Traefik) with HTTPS.
- [ ] Decide on access control — the app has none built in. The reverse proxy is the natural place.
- [ ] Pin `media/` to a persistent volume large enough for the job artifacts you expect (each job is a few MB to a few hundred MB).
- [ ] Pin `db_data` (SQLite) to a persistent volume, or migrate to Postgres for multi-worker deployments.

## Switching to Postgres

Replace the `DATABASES` block in `pocketdock/settings.py` with the standard Django Postgres config and add `psycopg2-binary` to `requirements.txt`. The schema is small — the migration is straightforward (`python manage.py migrate`).
