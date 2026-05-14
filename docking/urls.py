from django.urls import path

from . import views

app_name = "docking"

urlpatterns = [
    path("", views.upload_view, name="upload"),
    path("jobs/<int:job_id>/", views.job_detail_view, name="job_detail"),
    path("queue/", views.queue_view, name="queue"),
    # API endpoints
    path("api/jobs/", views.api_create_job, name="api_create_job"),
    path("api/jobs/<int:job_id>/status/", views.api_job_status, name="api_job_status"),
    path("api/jobs/<int:job_id>/results/", views.api_job_results, name="api_job_results"),
    path(
        "api/jobs/<int:job_id>/files/<path:filename>",
        views.api_serve_file,
        name="api_serve_file",
    ),
    path("api/queue/", views.api_queue, name="api_queue"),
]
