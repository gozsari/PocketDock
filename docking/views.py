import io
import mimetypes
import uuid
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.core.files.base import ContentFile
from django.db.models import Max, Min
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from rest_framework.decorators import api_view

from .forms import BatchDockingForm, DockingJobForm
from .models import DockingJob, DockingResult, Pocket
from .serializers import (
    DockingJobStatusSerializer,
    DockingResultSerializer,
    PocketSerializer,
)


# ---------------------------------------------------------------------------
# Queue helpers
# ---------------------------------------------------------------------------
RUNNING_STATUSES = ["running_p2rank", "running_prep", "running_vina", "running_refinement", "running_mmgbsa"]
DEFAULT_AVG_DURATION_S = 240  # 4 min — used until we have completed-job history


def avg_completed_duration_seconds(n=20):
    """Average wall-clock duration of the last n completed jobs."""
    qs = DockingJob.objects.filter(status="completed").order_by("-updated_at")[:n]
    durations = [(j.updated_at - j.created_at).total_seconds() for j in qs]
    return sum(durations) / len(durations) if durations else DEFAULT_AVG_DURATION_S


def queue_position(job):
    """1-indexed position among pending jobs. Returns None for non-pending jobs."""
    if job.status != "pending":
        return None
    return DockingJob.objects.filter(
        status="pending", created_at__lt=job.created_at
    ).count() + 1


def estimate_wait_seconds(job, concurrency=None):
    """Rough wait estimate for a pending job, in seconds."""
    pos = queue_position(job)
    if pos is None:
        return 0
    if concurrency is None:
        concurrency = settings.WORKER_CONCURRENCY
    running = DockingJob.objects.filter(status__in=RUNNING_STATUSES).count()
    avg = avg_completed_duration_seconds()
    # Total work ahead = (jobs running now + jobs queued ahead) * avg duration
    total_seconds = (running + pos - 1) * avg
    return int(total_seconds / max(concurrency, 1))


def upload_view(request):
    mode = request.POST.get("mode", "single") if request.method == "POST" else "single"

    if request.method == "POST" and mode == "batch":
        return _handle_batch_upload(request)

    if request.method == "POST":
        form = DockingJobForm(request.POST, request.FILES)
        if form.is_valid():
            job = form.save()
            if not _enqueue_pipeline(job):
                form.add_error(None,
                    "Job was created but could not be queued — the task broker is unreachable. "
                    "Please try again in a moment."
                )
                return render(request, "docking/upload.html", {"form": form, "batch_form": BatchDockingForm()})
            return redirect("docking:job_detail", job_id=job.id)
    else:
        form = DockingJobForm()
    return render(request, "docking/upload.html", {"form": form, "batch_form": BatchDockingForm()})


def _handle_batch_upload(request):
    """Process a batch upload (multiple ligand files or multi-mol SDF)."""
    batch_form = BatchDockingForm(request.POST, request.FILES)
    if not batch_form.is_valid():
        return render(request, "docking/upload.html", {
            "form": DockingJobForm(),
            "batch_form": batch_form,
            "active_tab": "batch",
        })

    protein_file = batch_form.cleaned_data["protein_file"]
    ligand_files = request.FILES.getlist("ligand_files")
    params = {
        "name": batch_form.cleaned_data.get("name", ""),
        "num_pockets": batch_form.cleaned_data["num_pockets"],
        "exhaustiveness": batch_form.cleaned_data["exhaustiveness"],
        "scoring_function": batch_form.cleaned_data["scoring_function"],
        "refine_poses": batch_form.cleaned_data.get("refine_poses", False),
        "rescore_mmgbsa": batch_form.cleaned_data.get("rescore_mmgbsa", False),
    }

    ligands = []
    for lf in ligand_files:
        if lf.name.lower().endswith(".sdf") and lf.size > 0:
            split = _split_multi_sdf(lf)
            if split:
                ligands.extend(split)
            else:
                lf.seek(0)
                ligands.append((Path(lf.name).stem, lf.read(), lf.name))
        else:
            ligands.append((Path(lf.name).stem, lf.read(), lf.name))

    if not ligands:
        batch_form.add_error(None, "No valid ligands found in the uploaded files.")
        return render(request, "docking/upload.html", {
            "form": DockingJobForm(),
            "batch_form": batch_form,
            "active_tab": "batch",
        })

    batch_id = _create_batch_jobs(protein_file, ligands, params)
    if batch_id is None:
        batch_form.add_error(None,
            "Batch was created but could not be queued — the task broker is unreachable. "
            "Please try again in a moment."
        )
        return render(request, "docking/upload.html", {
            "form": DockingJobForm(),
            "batch_form": batch_form,
            "active_tab": "batch",
        })

    return redirect("docking:batch_detail", batch_id=batch_id)


def _split_multi_sdf(sdf_file):
    """
    Split an SDF file into individual molecules.
    Returns list of (name, sdf_bytes, filename) tuples, or empty list if
    the file contains only one molecule.
    """
    sdf_file.seek(0)
    raw = sdf_file.read()
    if isinstance(raw, str):
        raw = raw.encode("utf-8")

    blocks = []
    current = []
    for line in raw.decode("utf-8", errors="replace").splitlines(True):
        current.append(line)
        if line.strip() == "$$$$":
            blocks.append("".join(current))
            current = []

    if len(blocks) <= 1:
        return []

    results = []
    for i, block in enumerate(blocks):
        lines = block.splitlines()
        mol_name = lines[0].strip() if lines and lines[0].strip() else f"mol_{i + 1}"
        filename = f"{mol_name}.sdf"
        results.append((mol_name, block.encode("utf-8"), filename))
    return results


def _create_batch_jobs(protein_file, ligands, params):
    """
    Create one DockingJob per ligand, all sharing the same batch_id.
    Returns the batch_id on success, or None if enqueueing fails.
    """
    batch_id = uuid.uuid4().hex[:12]
    protein_bytes = protein_file.read()
    protein_name = protein_file.name
    batch_name = params.get("name", "")

    jobs = []
    for lig_name, lig_content, lig_filename in ligands:
        job = DockingJob(
            name=f"{batch_name} - {lig_name}" if batch_name else lig_name,
            batch_id=batch_id,
            ligand_name=lig_name,
            num_pockets=params["num_pockets"],
            exhaustiveness=params["exhaustiveness"],
            scoring_function=params["scoring_function"],
            refine_poses=params.get("refine_poses", False),
            rescore_mmgbsa=params.get("rescore_mmgbsa", False),
        )
        job.save()
        job.protein_file.save(protein_name, ContentFile(protein_bytes), save=True)
        job.ligand_file.save(lig_filename, ContentFile(lig_content), save=True)
        jobs.append(job)

    enqueued = 0
    for job in jobs:
        if _enqueue_pipeline(job):
            enqueued += 1

    return batch_id if enqueued > 0 else None


def _enqueue_pipeline(job):
    """Dispatch the Celery pipeline. On broker failure, delete the orphaned job and return False."""
    from .tasks import run_docking_pipeline
    try:
        task = run_docking_pipeline.delay(job.id)
    except Exception:
        job.delete()
        return False
    job.celery_task_id = task.id
    job.save(update_fields=["celery_task_id"])
    return True


def job_detail_view(request, job_id):
    job = get_object_or_404(DockingJob, id=job_id)
    view_mode = request.GET.get("view", "")

    if job.status == DockingJob.Status.COMPLETED and view_mode == "results":
        return render(request, "docking/results.html", {"job": job})
    elif job.status == DockingJob.Status.COMPLETED and view_mode != "status":
        return render(request, "docking/results.html", {"job": job})
    else:
        ctx = {"job": job}
        if job.status == "pending":
            ctx["queue_position"] = queue_position(job)
            ctx["estimated_wait_seconds"] = estimate_wait_seconds(job)
        return render(request, "docking/status.html", ctx)


@api_view(["GET"])
def api_job_status(request, job_id):
    job = get_object_or_404(DockingJob, id=job_id)
    serializer = DockingJobStatusSerializer(job)
    data = dict(serializer.data)
    if job.status == "pending":
        data["queue_position"] = queue_position(job)
        data["estimated_wait_seconds"] = estimate_wait_seconds(job)
    return JsonResponse(data)


@api_view(["GET"])
def api_job_results(request, job_id):
    job = get_object_or_404(DockingJob, id=job_id)
    pockets = Pocket.objects.filter(job=job)
    results = DockingResult.objects.filter(pocket__job=job).select_related("pocket")

    data = {
        "job_id": job.id,
        "status": job.status,
        "complete": job.status == DockingJob.Status.COMPLETED,
        "protein_file": job.protein_filename,
        "ligand_file": job.ligand_filename,
        "scoring_function": job.get_scoring_function_display(),
        "admet": job.admet_properties or {},
        "pockets": PocketSerializer(pockets, many=True).data,
        "results": DockingResultSerializer(results, many=True).data,
    }
    return JsonResponse(data)


@api_view(["POST"])
def api_create_job(request):
    form = DockingJobForm(request.POST, request.FILES)
    if form.is_valid():
        job = form.save()
        if not _enqueue_pipeline(job):
            return JsonResponse(
                {"job_id": job.id, "status": job.status, "error": job.error_message},
                status=503,
            )
        return JsonResponse({"job_id": job.id, "status": job.status}, status=201)
    return JsonResponse({"errors": form.errors}, status=400)


@require_http_methods(["GET", "HEAD"])
def api_serve_file(request, job_id, filename):
    """Serve molecular files (PDB, PDBQT, SDF) for the 3D viewer."""
    job = get_object_or_404(DockingJob, id=job_id)
    job_path = job.job_path

    # Security: prevent directory traversal
    safe_path = (job_path / filename).resolve()
    if not str(safe_path).startswith(str(job_path.resolve())):
        raise Http404("Invalid file path.")

    if not safe_path.exists():
        raise Http404(f"File not found: {filename}")

    content_type, _ = mimetypes.guess_type(str(safe_path))
    if content_type is None:
        content_type = "text/plain"

    try:
        return FileResponse(open(safe_path, "rb"), content_type=content_type)
    except OSError:
        raise Http404(f"Cannot read file: {filename}")


# ---------------------------------------------------------------------------
# Batch views
# ---------------------------------------------------------------------------
def batch_detail_view(request, batch_id):
    """Render the batch dashboard for all jobs sharing a batch_id."""
    jobs = DockingJob.objects.filter(batch_id=batch_id).order_by("id")
    if not jobs.exists():
        raise Http404("Batch not found.")

    first_job = jobs.first()
    total = jobs.count()
    completed = jobs.filter(status="completed").count()
    failed = jobs.filter(status="failed").count()
    running = jobs.filter(status__in=RUNNING_STATUSES).count()
    pending = jobs.filter(status="pending").count()

    job_summaries = []
    for job in jobs:
        best = DockingResult.objects.filter(
            pocket__job=job
        ).aggregate(
            best_affinity=Min("affinity"),
            best_score=Max("combined_score"),
        )
        job_summaries.append({
            "job": job,
            "best_affinity": best["best_affinity"],
            "best_score": best["best_score"],
        })

    ctx = {
        "batch_id": batch_id,
        "batch_name": first_job.name.rsplit(" - ", 1)[0] if " - " in first_job.name else "",
        "protein_filename": first_job.protein_filename,
        "total": total,
        "completed": completed,
        "failed": failed,
        "running": running,
        "pending": pending,
        "progress_pct": int(100 * (completed + failed) / total) if total else 0,
        "all_done": (completed + failed) == total,
        "job_summaries": job_summaries,
        "first_job": first_job,
    }
    return render(request, "docking/batch.html", ctx)


@api_view(["GET"])
def api_batch_status(request, batch_id):
    """JSON endpoint returning status of all jobs in a batch."""
    jobs = DockingJob.objects.filter(batch_id=batch_id).order_by("id")
    if not jobs.exists():
        return JsonResponse({"error": "Batch not found"}, status=404)

    total = jobs.count()
    completed = jobs.filter(status="completed").count()
    failed = jobs.filter(status="failed").count()

    job_list = []
    for job in jobs:
        best = DockingResult.objects.filter(
            pocket__job=job
        ).aggregate(
            best_affinity=Min("affinity"),
            best_score=Max("combined_score"),
        )
        job_list.append({
            "id": job.id,
            "ligand_name": job.ligand_name,
            "status": job.status,
            "status_display": job.get_status_display(),
            "best_affinity": best["best_affinity"],
            "best_score": round(best["best_score"], 3) if best["best_score"] else None,
        })

    return JsonResponse({
        "batch_id": batch_id,
        "total": total,
        "completed": completed,
        "failed": failed,
        "running": total - completed - failed - jobs.filter(status="pending").count(),
        "pending": jobs.filter(status="pending").count(),
        "progress_pct": int(100 * (completed + failed) / total) if total else 0,
        "all_done": (completed + failed) == total,
        "jobs": job_list,
    })


# ---------------------------------------------------------------------------
# Public queue page (redacted)
# ---------------------------------------------------------------------------
def _queue_querysets():
    """Build the three job querysets shown on the queue page."""
    pending = DockingJob.objects.filter(status="pending").order_by("created_at")
    running = DockingJob.objects.filter(status__in=RUNNING_STATUSES).order_by("created_at")
    cutoff = timezone.now() - timedelta(hours=24)
    recent = DockingJob.objects.filter(
        status__in=["completed", "failed"], updated_at__gte=cutoff
    ).order_by("-updated_at")[:50]
    return pending, running, recent, cutoff


def _queue_context():
    pending, running, recent, cutoff = _queue_querysets()
    return {
        "pending_jobs": pending,
        "running_jobs": running,
        "recent_jobs": recent,
        "pending_count": pending.count(),
        "running_count": running.count(),
        "completed_today_count": DockingJob.objects.filter(
            status="completed", updated_at__gte=cutoff
        ).count(),
        "worker_concurrency": settings.WORKER_CONCURRENCY,
        "avg_duration_seconds": int(avg_completed_duration_seconds()),
    }


def queue_view(request):
    """Render the public, redacted queue page."""
    return render(request, "docking/queue.html", _queue_context())


def _redacted_job_dict(job, position=None):
    """Build a JSON-safe dict with no user-supplied fields."""
    d = {
        "id": job.id,
        "status": job.status,
        "status_display": job.get_status_display(),
        "created_at": job.created_at.isoformat(),
        "updated_at": job.updated_at.isoformat(),
    }
    if job.status in ("completed", "failed"):
        d["duration_seconds"] = int((job.updated_at - job.created_at).total_seconds())
    if position is not None:
        d["queue_position"] = position
    return d


@api_view(["GET"])
def api_queue(request):
    """JSON version of the queue page — same redaction rules."""
    pending, running, recent, _ = _queue_querysets()
    pending_list = list(pending)
    return JsonResponse({
        "pending_count": len(pending_list),
        "running_count": running.count(),
        "completed_today_count": DockingJob.objects.filter(
            status="completed",
            updated_at__gte=timezone.now() - timedelta(hours=24),
        ).count(),
        "worker_concurrency": settings.WORKER_CONCURRENCY,
        "avg_duration_seconds": int(avg_completed_duration_seconds()),
        "running": [_redacted_job_dict(j) for j in running],
        "pending": [_redacted_job_dict(j, position=i + 1)
                    for i, j in enumerate(pending_list)],
        "recent": [_redacted_job_dict(j) for j in recent],
    })
