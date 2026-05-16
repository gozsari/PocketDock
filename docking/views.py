import mimetypes
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from rest_framework.decorators import api_view

from .forms import DockingJobForm
from .models import DockingJob, DockingResult, Pocket
from .serializers import (
    DockingJobStatusSerializer,
    DockingResultSerializer,
    PocketSerializer,
)


# ---------------------------------------------------------------------------
# Queue helpers
# ---------------------------------------------------------------------------
RUNNING_STATUSES = ["running_p2rank", "running_prep", "running_vina", "running_refinement"]
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
    if request.method == "POST":
        form = DockingJobForm(request.POST, request.FILES)
        if form.is_valid():
            job = form.save()
            if not _enqueue_pipeline(job):
                # Re-render the form with a clear error so the user knows to retry.
                form.add_error(None,
                    "Job was created but could not be queued — the task broker is unreachable. "
                    "Please try again in a moment."
                )
                return render(request, "docking/upload.html", {"form": form})
            return redirect("docking:job_detail", job_id=job.id)
    else:
        form = DockingJobForm()
    return render(request, "docking/upload.html", {"form": form})


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
