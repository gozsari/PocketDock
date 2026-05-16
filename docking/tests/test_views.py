import pytest
from django.test import Client
from django.urls import reverse

from docking.models import DockingJob


@pytest.mark.django_db
class TestUploadView:
    def test_get(self):
        client = Client()
        resp = client.get(reverse("docking:upload"))
        assert resp.status_code == 200

    def test_post_no_files(self):
        client = Client()
        resp = client.post(reverse("docking:upload"), data={"num_pockets": 3, "exhaustiveness": 8})
        assert resp.status_code == 200
        assert b"error" in resp.content.lower() or b"required" in resp.content.lower()


@pytest.mark.django_db
class TestJobDetailView:
    def test_completed_job_shows_results(self, sample_job):
        sample_job.status = DockingJob.Status.COMPLETED
        sample_job.save()
        client = Client()
        resp = client.get(reverse("docking:job_detail", args=[sample_job.id]))
        assert resp.status_code == 200

    def test_pending_job_shows_status(self, sample_job):
        client = Client()
        resp = client.get(reverse("docking:job_detail", args=[sample_job.id]))
        assert resp.status_code == 200
        assert b"Pocket" in resp.content

    def test_nonexistent_job_404(self):
        client = Client()
        resp = client.get(reverse("docking:job_detail", args=[99999]))
        assert resp.status_code == 404


@pytest.mark.django_db
class TestAPIJobStatus:
    def test_status_endpoint(self, sample_job):
        client = Client()
        resp = client.get(reverse("docking:api_job_status", args=[sample_job.id]))
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "pending"


@pytest.mark.django_db
class TestAPIJobResults:
    def test_results_endpoint(self, sample_job, sample_result):
        sample_job.status = DockingJob.Status.COMPLETED
        sample_job.save()
        client = Client()
        resp = client.get(reverse("docking:api_job_results", args=[sample_job.id]))
        assert resp.status_code == 200
        data = resp.json()
        assert data["complete"] is True
        assert len(data["results"]) == 1


@pytest.mark.django_db
class TestAPIServeFile:
    def test_traversal_attempt(self, sample_job):
        client = Client()
        resp = client.get(
            reverse("docking:api_serve_file", args=[sample_job.id, "../../etc/passwd"])
        )
        assert resp.status_code == 404

    def test_missing_file(self, sample_job):
        client = Client()
        resp = client.get(
            reverse("docking:api_serve_file", args=[sample_job.id, "nonexistent.pdb"])
        )
        assert resp.status_code == 404
