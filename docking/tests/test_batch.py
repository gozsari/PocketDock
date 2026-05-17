import pytest
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse

from docking.models import DockingJob, DockingResult, Pocket
from docking.views import _split_multi_sdf


PROTEIN_PDB = b"ATOM      1  N   ALA A   1       0.0   0.0   0.0  1.00  0.00           N\nEND\n"
SINGLE_SDF = b"\n  SDF\n\n  1  0  0  0  0  0  0  0  0  0  1 V2000\n    0.0    0.0    0.0 C   0  0\nM  END\n$$$$\n"
MULTI_SDF = (
    b"aspirin\n  SDF\n\n  1  0  0  0  0  0  0  0  0  0  1 V2000\n"
    b"    0.0    0.0    0.0 C   0  0\nM  END\n$$$$\n"
    b"ibuprofen\n  SDF\n\n  1  0  0  0  0  0  0  0  0  0  1 V2000\n"
    b"    1.0    1.0    1.0 C   0  0\nM  END\n$$$$\n"
    b"caffeine\n  SDF\n\n  1  0  0  0  0  0  0  0  0  0  1 V2000\n"
    b"    2.0    2.0    2.0 C   0  0\nM  END\n$$$$\n"
)


class TestSplitMultiSDF:
    def test_splits_multi_molecule_sdf(self):
        f = SimpleUploadedFile("library.sdf", MULTI_SDF, content_type="chemical/x-mdl-sdfile")
        result = _split_multi_sdf(f)
        assert len(result) == 3
        assert result[0][0] == "aspirin"
        assert result[1][0] == "ibuprofen"
        assert result[2][0] == "caffeine"
        for name, content, filename in result:
            assert b"$$$$" in content
            assert filename.endswith(".sdf")

    def test_returns_empty_for_single_molecule(self):
        f = SimpleUploadedFile("single.sdf", SINGLE_SDF, content_type="chemical/x-mdl-sdfile")
        result = _split_multi_sdf(f)
        assert result == []

    def test_returns_empty_for_empty_file(self):
        f = SimpleUploadedFile("empty.sdf", b"", content_type="chemical/x-mdl-sdfile")
        result = _split_multi_sdf(f)
        assert result == []


@pytest.mark.django_db
class TestBatchJobCreation:
    def test_batch_upload_creates_multiple_jobs(self):
        client = Client()

        protein = SimpleUploadedFile("protein.pdb", PROTEIN_PDB)
        ligand = SimpleUploadedFile("library.sdf", MULTI_SDF, content_type="chemical/x-mdl-sdfile")

        with patch("docking.views._enqueue_pipeline", return_value=True):
            resp = client.post(reverse("docking:upload"), {
                "mode": "batch",
                "name": "Test Batch",
                "protein_file": protein,
                "ligand_files": ligand,
                "num_pockets": 3,
                "exhaustiveness": 8,
                "scoring_function": "vina",
            })

        assert resp.status_code == 302
        batch_jobs = DockingJob.objects.filter(batch_id__isnull=False).exclude(batch_id="")
        assert batch_jobs.count() == 3

        batch_id = batch_jobs.first().batch_id
        assert all(j.batch_id == batch_id for j in batch_jobs)
        names = sorted(j.ligand_name for j in batch_jobs)
        assert names == ["aspirin", "caffeine", "ibuprofen"]

    def test_batch_upload_multiple_files(self):
        client = Client()

        protein = SimpleUploadedFile("protein.pdb", PROTEIN_PDB)
        lig1 = SimpleUploadedFile("mol_a.mol2", b"mol2 content", content_type="chemical/x-mol2")
        lig2 = SimpleUploadedFile("mol_b.mol2", b"mol2 content 2", content_type="chemical/x-mol2")

        with patch("docking.views._enqueue_pipeline", return_value=True):
            resp = client.post(reverse("docking:upload"), {
                "mode": "batch",
                "name": "Multi File Batch",
                "protein_file": protein,
                "ligand_files": [lig1, lig2],
                "num_pockets": 2,
                "exhaustiveness": 4,
                "scoring_function": "vina",
            })

        assert resp.status_code == 302
        batch_jobs = DockingJob.objects.filter(batch_id__isnull=False).exclude(batch_id="")
        assert batch_jobs.count() == 2
        names = sorted(j.ligand_name for j in batch_jobs)
        assert names == ["mol_a", "mol_b"]


@pytest.mark.django_db
class TestBatchDashboard:
    def _create_batch(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        batch_id = "test_batch_1"
        jobs = []
        for i, name in enumerate(["aspirin", "ibuprofen"]):
            job = DockingJob.objects.create(
                name=f"Test - {name}",
                batch_id=batch_id,
                ligand_name=name,
                protein_file=SimpleUploadedFile("protein.pdb", PROTEIN_PDB),
                ligand_file=SimpleUploadedFile(f"{name}.sdf", SINGLE_SDF),
            )
            jobs.append(job)
        return batch_id, jobs

    def test_batch_detail_view(self):
        batch_id, jobs = self._create_batch()
        client = Client()
        resp = client.get(reverse("docking:batch_detail", args=[batch_id]))
        assert resp.status_code == 200
        assert b"aspirin" in resp.content
        assert b"ibuprofen" in resp.content

    def test_batch_detail_404_for_unknown_id(self):
        client = Client()
        resp = client.get(reverse("docking:batch_detail", args=["nonexistent"]))
        assert resp.status_code == 404

    def test_api_batch_status(self):
        batch_id, jobs = self._create_batch()
        jobs[0].status = DockingJob.Status.COMPLETED
        jobs[0].save()

        pocket = Pocket.objects.create(
            job=jobs[0], rank=1, score=10.0, probability=0.9,
            center_x=0, center_y=0, center_z=0,
        )
        DockingResult.objects.create(
            pocket=pocket, pose_rank=1, affinity=-7.5, combined_score=0.6,
        )

        client = Client()
        resp = client.get(reverse("docking:api_batch_status", args=[batch_id]))
        data = resp.json()

        assert data["total"] == 2
        assert data["completed"] == 1
        assert data["all_done"] is False
        assert len(data["jobs"]) == 2
        completed_job = next(j for j in data["jobs"] if j["status"] == "completed")
        assert completed_job["best_affinity"] == -7.5

    def test_api_batch_status_404(self):
        client = Client()
        resp = client.get(reverse("docking:api_batch_status", args=["nope"]))
        assert resp.status_code == 404


@pytest.mark.django_db
class TestSingleLigandRegression:
    """Ensure single-ligand uploads still work unchanged."""

    def test_single_upload_still_works(self):
        client = Client()
        protein = SimpleUploadedFile("protein.pdb", PROTEIN_PDB)
        ligand = SimpleUploadedFile("ligand.sdf", SINGLE_SDF)

        with patch("docking.views._enqueue_pipeline", return_value=True):
            resp = client.post(reverse("docking:upload"), {
                "mode": "single",
                "name": "Single Job",
                "protein_file": protein,
                "ligand_file": ligand,
                "num_pockets": 3,
                "exhaustiveness": 8,
                "scoring_function": "vina",
            })

        assert resp.status_code == 302
        job = DockingJob.objects.get(name="Single Job")
        assert job.batch_id == ""
        assert job.ligand_name == ""

    def test_upload_page_renders(self):
        client = Client()
        resp = client.get(reverse("docking:upload"))
        assert resp.status_code == 200
        assert b"Single Ligand" in resp.content
        assert b"Batch Docking" in resp.content
