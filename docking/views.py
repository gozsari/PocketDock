import mimetypes
from pathlib import Path

from django.conf import settings
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from rest_framework.decorators import api_view

from .forms import DockingJobForm
from .models import DockingJob, DockingResult, Pocket
from .serializers import (
    DockingJobStatusSerializer,
    DockingResultSerializer,
    PocketSerializer,
)


def upload_view(request):
    if request.method == "POST":
        form = DockingJobForm(request.POST, request.FILES)
        if form.is_valid():
            job = form.save()
            # Dispatch the pipeline task
            from .tasks import run_docking_pipeline
            task = run_docking_pipeline.delay(job.id)
            job.celery_task_id = task.id
            job.save(update_fields=["celery_task_id"])
            return redirect("docking:job_detail", job_id=job.id)
    else:
        form = DockingJobForm()
    return render(request, "docking/upload.html", {"form": form})


def job_detail_view(request, job_id):
    job = get_object_or_404(DockingJob, id=job_id)
    view_mode = request.GET.get("view", "")

    if job.status == DockingJob.Status.COMPLETED and view_mode == "results":
        return render(request, "docking/results.html", {"job": job})
    elif job.status == DockingJob.Status.COMPLETED and view_mode != "status":
        return render(request, "docking/results.html", {"job": job})
    else:
        return render(request, "docking/status.html", {"job": job})


@api_view(["GET"])
def api_job_status(request, job_id):
    job = get_object_or_404(DockingJob, id=job_id)
    serializer = DockingJobStatusSerializer(job)
    return JsonResponse(serializer.data)


@api_view(["GET"])
def api_job_results(request, job_id):
    job = get_object_or_404(DockingJob, id=job_id)
    pockets = Pocket.objects.filter(job=job)
    results = DockingResult.objects.filter(pocket__job=job).select_related("pocket")

    return JsonResponse({
        "job_id": job.id,
        "status": job.status,
        "protein_file": job.protein_filename,
        "ligand_file": job.ligand_filename,
        "pockets": PocketSerializer(pockets, many=True).data,
        "results": DockingResultSerializer(results, many=True).data,
    })


@api_view(["POST"])
def api_create_job(request):
    form = DockingJobForm(request.POST, request.FILES)
    if form.is_valid():
        job = form.save()
        from .tasks import run_docking_pipeline
        task = run_docking_pipeline.delay(job.id)
        job.celery_task_id = task.id
        job.save(update_fields=["celery_task_id"])
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

    return FileResponse(open(safe_path, "rb"), content_type=content_type)
