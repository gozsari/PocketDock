from unittest.mock import MagicMock, patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse

from docking.models import DockingJob, DockingResult, Pocket

PROTEIN_PDB = b"ATOM      1  N   ALA A   1       0.0   0.0   0.0  1.00  0.00           N\nEND\n"
SINGLE_SDF = b"\n  SDF\n\n  1  0  0  0  0  0  0  0  0  0  1 V2000\n    0.0    0.0    0.0 C   0  0\nM  END\n$$$$\n"


def _make_parent_job(db, *, method="nma", n_confs=3):
    job = DockingJob.objects.create(
        name="Ensemble Test",
        protein_file=SimpleUploadedFile("protein.pdb", PROTEIN_PDB),
        ligand_file=SimpleUploadedFile("ligand.sdf", SINGLE_SDF),
        ensemble_method=method,
        num_conformations=n_confs,
    )
    return job


def _create_ensemble(db, *, method="nma", n_confs=3):
    """Create a parent + N children sharing an ensemble_id."""
    ensemble_id = "test_ens_001"
    parent = DockingJob.objects.create(
        name="Ensemble Test",
        protein_file=SimpleUploadedFile("protein.pdb", PROTEIN_PDB),
        ligand_file=SimpleUploadedFile("ligand.sdf", SINGLE_SDF),
        ensemble_id=ensemble_id,
        ensemble_method=method,
        conformation_index=0,
        num_conformations=n_confs,
        status=DockingJob.Status.COMPLETED,
    )
    children = []
    for i in range(1, n_confs + 1):
        child = DockingJob.objects.create(
            name=f"Ensemble Test - conf {i}",
            protein_file=SimpleUploadedFile(f"conf_{i}.pdb", PROTEIN_PDB),
            ligand_file=SimpleUploadedFile("ligand.sdf", SINGLE_SDF),
            ensemble_id=ensemble_id,
            ensemble_method=method,
            conformation_index=i,
            num_conformations=n_confs,
        )
        children.append(child)
    return ensemble_id, parent, children


@pytest.mark.django_db
class TestEnsembleModel:
    def test_ensemble_fields_default(self):
        job = DockingJob.objects.create(
            name="Regular Job",
            protein_file=SimpleUploadedFile("protein.pdb", PROTEIN_PDB),
            ligand_file=SimpleUploadedFile("ligand.sdf", SINGLE_SDF),
        )
        assert job.ensemble_method == "none"
        assert job.ensemble_id == ""
        assert job.conformation_index == 0
        assert job.num_conformations == 5

    def test_ensemble_status_choice_exists(self):
        assert DockingJob.Status.RUNNING_ENSEMBLE == "running_ensemble"

    def test_ensemble_method_choices(self):
        assert DockingJob.EnsembleMethod.NONE == "none"
        assert DockingJob.EnsembleMethod.NMA == "nma"
        assert DockingJob.EnsembleMethod.MD == "md"

    def test_ensemble_id_indexed(self):
        field = DockingJob._meta.get_field("ensemble_id")
        assert field.db_index


@pytest.mark.django_db
class TestEnsemblePipeline:
    def test_parent_job_spawns_children(self):
        """_run_ensemble_docking creates child jobs and enqueues them."""
        job = _make_parent_job(None, method="nma", n_confs=3)

        mock_conf_paths = []
        for i in range(3):
            p = MagicMock()
            p.read_bytes.return_value = PROTEIN_PDB
            p.name = f"conf_{i + 1}.pdb"
            mock_conf_paths.append(p)

        with (
            patch("docking.tasks._generate_conformations_nma", return_value=mock_conf_paths),
            patch("docking.tasks.run_docking_pipeline") as mock_task,
        ):
            mock_task.delay = MagicMock(return_value=MagicMock(id="fake-task-id"))

            from docking.tasks import _run_ensemble_docking

            _run_ensemble_docking(job)

        job.refresh_from_db()
        assert job.status == DockingJob.Status.COMPLETED
        assert job.ensemble_id != ""
        assert mock_task.delay.call_count == 3

        children = DockingJob.objects.filter(
            ensemble_id=job.ensemble_id,
            conformation_index__gt=0,
        )
        assert children.count() == 3
        for child in children:
            assert child.ensemble_method == "nma"
            assert child.num_conformations == 3

    def test_parent_md_job_calls_md_generator(self):
        """Ensemble with MD method calls _generate_conformations_md."""
        job = _make_parent_job(None, method="md", n_confs=2)

        mock_conf_paths = []
        for i in range(2):
            p = MagicMock()
            p.read_bytes.return_value = PROTEIN_PDB
            p.name = f"conf_{i + 1}.pdb"
            mock_conf_paths.append(p)

        with (
            patch(
                "docking.tasks._generate_conformations_md", return_value=mock_conf_paths
            ) as mock_md,
            patch("docking.tasks._generate_conformations_nma") as mock_nma,
            patch("docking.tasks.run_docking_pipeline") as mock_task,
        ):
            mock_task.delay = MagicMock(return_value=MagicMock(id="fake-id"))

            from docking.tasks import _run_ensemble_docking

            _run_ensemble_docking(job)

        mock_md.assert_called_once()
        mock_nma.assert_not_called()

    def test_pipeline_routes_parent_to_ensemble(self):
        """Parent job (conformation_index=0, method!=none) is routed to ensemble logic."""
        job = _make_parent_job(None, method="nma", n_confs=2)

        with patch("docking.tasks._run_ensemble_docking") as mock_ens:
            from docking.tasks import run_docking_pipeline

            run_docking_pipeline(job.id)

        mock_ens.assert_called_once()

    def test_pipeline_routes_child_normally(self):
        """Child job (conformation_index>0) runs the standard docking pipeline."""
        job = DockingJob.objects.create(
            name="Ensemble Child",
            protein_file=SimpleUploadedFile("conf_1.pdb", PROTEIN_PDB),
            ligand_file=SimpleUploadedFile("ligand.sdf", SINGLE_SDF),
            ensemble_method="nma",
            conformation_index=1,
            ensemble_id="test_ens",
        )

        with (
            patch("docking.tasks._run_p2rank") as mock_p2rank,
            patch("docking.tasks._run_structure_prep"),
            patch("docking.tasks._compute_admet_properties"),
            patch("docking.tasks._run_vina_docking"),
            patch("docking.tasks._run_interaction_analysis"),
        ):
            from docking.tasks import run_docking_pipeline

            run_docking_pipeline(job.id)

        mock_p2rank.assert_called_once()
        job.refresh_from_db()
        assert job.status == DockingJob.Status.COMPLETED

    def test_non_ensemble_job_skips_ensemble_logic(self):
        """Job with ensemble_method='none' goes through normal pipeline."""
        job = DockingJob.objects.create(
            name="Normal Job",
            protein_file=SimpleUploadedFile("protein.pdb", PROTEIN_PDB),
            ligand_file=SimpleUploadedFile("ligand.sdf", SINGLE_SDF),
            ensemble_method="none",
        )

        with (
            patch("docking.tasks._run_ensemble_docking") as mock_ens,
            patch("docking.tasks._run_p2rank"),
            patch("docking.tasks._run_structure_prep"),
            patch("docking.tasks._compute_admet_properties"),
            patch("docking.tasks._run_vina_docking"),
            patch("docking.tasks._run_interaction_analysis"),
        ):
            from docking.tasks import run_docking_pipeline

            run_docking_pipeline(job.id)

        mock_ens.assert_not_called()


@pytest.mark.django_db
class TestEnsembleDashboard:
    def test_ensemble_detail_view(self):
        ensemble_id, parent, children = _create_ensemble(None)
        client = Client()
        resp = client.get(reverse("docking:ensemble_detail", args=[ensemble_id]))
        assert resp.status_code == 200
        assert b"Ensemble" in resp.content

    def test_ensemble_detail_404_for_unknown_id(self):
        client = Client()
        resp = client.get(reverse("docking:ensemble_detail", args=["nonexistent"]))
        assert resp.status_code == 404

    def test_api_ensemble_status(self):
        ensemble_id, parent, children = _create_ensemble(None)
        children[0].status = DockingJob.Status.COMPLETED
        children[0].save()

        pocket = Pocket.objects.create(
            job=children[0],
            rank=1,
            score=10.0,
            probability=0.9,
            center_x=0,
            center_y=0,
            center_z=0,
        )
        DockingResult.objects.create(
            pocket=pocket,
            pose_rank=1,
            affinity=-7.5,
            combined_score=0.6,
        )

        client = Client()
        resp = client.get(reverse("docking:api_ensemble_status", args=[ensemble_id]))
        data = resp.json()

        assert data["total"] == 3
        assert data["completed"] == 1
        assert data["all_done"] is False
        assert len(data["conformations"]) == 3
        assert len(data["best_results"]) >= 1

        completed_conf = next(c for c in data["conformations"] if c["status"] == "completed")
        assert completed_conf["best_affinity"] == -7.5

    def test_api_ensemble_status_all_done(self):
        ensemble_id, parent, children = _create_ensemble(None)
        for child in children:
            child.status = DockingJob.Status.COMPLETED
            child.save()

        client = Client()
        resp = client.get(reverse("docking:api_ensemble_status", args=[ensemble_id]))
        data = resp.json()
        assert data["all_done"] is True
        assert data["progress_pct"] == 100

    def test_api_ensemble_status_404(self):
        client = Client()
        resp = client.get(reverse("docking:api_ensemble_status", args=["nope"]))
        assert resp.status_code == 404

    def test_parent_job_redirects_to_ensemble_dashboard(self):
        ensemble_id, parent, children = _create_ensemble(None)
        client = Client()
        resp = client.get(reverse("docking:job_detail", args=[parent.id]))
        assert resp.status_code == 302
        assert ensemble_id in resp.url

    def test_child_job_shows_results_not_redirect(self):
        ensemble_id, parent, children = _create_ensemble(None)
        children[0].status = DockingJob.Status.COMPLETED
        children[0].save()
        client = Client()
        resp = client.get(reverse("docking:job_detail", args=[children[0].id]))
        assert resp.status_code == 200


@pytest.mark.django_db
class TestEnsembleRegression:
    """Ensure non-ensemble jobs are completely unaffected."""

    def test_single_upload_no_ensemble(self):
        client = Client()
        protein = SimpleUploadedFile("protein.pdb", PROTEIN_PDB)
        ligand = SimpleUploadedFile("ligand.sdf", SINGLE_SDF)

        with patch("docking.views._enqueue_pipeline", return_value=True):
            resp = client.post(
                reverse("docking:upload"),
                {
                    "mode": "single",
                    "name": "Normal Job",
                    "protein_file": protein,
                    "ligand_file": ligand,
                    "num_pockets": 3,
                    "exhaustiveness": 8,
                    "scoring_function": "vina",
                },
            )

        assert resp.status_code == 302
        job = DockingJob.objects.get(name="Normal Job")
        assert job.ensemble_method == "none"
        assert job.ensemble_id == ""
        assert job.conformation_index == 0

    def test_regular_completed_job_shows_results(self):
        job = DockingJob.objects.create(
            name="Done Job",
            protein_file=SimpleUploadedFile("protein.pdb", PROTEIN_PDB),
            ligand_file=SimpleUploadedFile("ligand.sdf", SINGLE_SDF),
            status=DockingJob.Status.COMPLETED,
        )
        client = Client()
        resp = client.get(reverse("docking:job_detail", args=[job.id]))
        assert resp.status_code == 200

    def test_upload_page_shows_ensemble_options(self):
        client = Client()
        resp = client.get(reverse("docking:upload"))
        assert resp.status_code == 200
        assert b"Ensemble Docking" in resp.content
        assert b"ensemble_enabled" in resp.content

    def test_single_upload_with_ensemble_enabled(self):
        client = Client()
        protein = SimpleUploadedFile("protein.pdb", PROTEIN_PDB)
        ligand = SimpleUploadedFile("ligand.sdf", SINGLE_SDF)

        with patch("docking.views._enqueue_pipeline", return_value=True):
            resp = client.post(
                reverse("docking:upload"),
                {
                    "mode": "single",
                    "name": "Ensemble Job",
                    "protein_file": protein,
                    "ligand_file": ligand,
                    "num_pockets": 3,
                    "exhaustiveness": 8,
                    "scoring_function": "vina",
                    "ensemble_enabled": True,
                    "ensemble_method": "nma",
                    "num_conformations": 5,
                },
            )

        assert resp.status_code == 302
        job = DockingJob.objects.get(name="Ensemble Job")
        assert job.ensemble_method == "nma"
        assert job.num_conformations == 5
