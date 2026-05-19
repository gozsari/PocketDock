from unittest.mock import MagicMock, patch

import pytest

from docking.models import DockingJob


def _mock_rdkit_numpy():
    """Return sys.modules patches so rdkit/numpy imports inside tasks succeed."""
    mock_np = MagicMock()
    mock_rdkit = MagicMock()
    mock_chem = MagicMock()
    mock_allchem = MagicMock()
    mock_geom = MagicMock()
    mock_rdkit.Chem = mock_chem
    mock_chem.AllChem = mock_allchem
    return {
        "numpy": mock_np,
        "rdkit": mock_rdkit,
        "rdkit.Chem": mock_chem,
        "rdkit.Chem.AllChem": mock_allchem,
        "rdkit.Geometry": mock_geom,
    }


FAKE_LIGAND_TEMPLATE_DATA = {
    "mol_with_h": MagicMock(),
    "charges": [],
    "radii": [],
}


@pytest.mark.django_db
class TestMMGBSARescoring:
    def test_sets_status_running_mmgbsa(self, sample_job, sample_result):
        from docking.tasks import _run_mmgbsa_rescoring

        pose_dir = sample_job.job_path / "results"
        pose_dir.mkdir(parents=True, exist_ok=True)
        pose_file = (
            pose_dir / f"pocket_{sample_result.pocket.rank}_pose_{sample_result.pose_rank}.pdb"
        )
        pose_file.write_text(
            "ATOM      1  C   LIG A   1       0.0   0.0   0.0  1.00  0.00           C\nEND\n"
        )

        mock_template = MagicMock()
        with (
            patch.dict("sys.modules", _mock_rdkit_numpy()),
            patch(
                "docking.tasks._parse_protein_for_mmgbsa",
                return_value={"coords": [], "charges": [], "radii": []},
            ),
            patch("docking.tasks._prepare_ligand_template", return_value=FAKE_LIGAND_TEMPLATE_DATA),
            patch("docking.tasks._compute_mmgbsa_single", return_value=-42.5),
        ):
            from rdkit import Chem

            Chem.MolFromMolFile = MagicMock(return_value=mock_template)
            _run_mmgbsa_rescoring(sample_job)

        sample_job.refresh_from_db()
        assert sample_job.status == DockingJob.Status.RUNNING_MMGBSA

    def test_stores_mmgbsa_score(self, sample_job, sample_result):
        from docking.tasks import _run_mmgbsa_rescoring

        pose_dir = sample_job.job_path / "results"
        pose_dir.mkdir(parents=True, exist_ok=True)
        pose_file = (
            pose_dir / f"pocket_{sample_result.pocket.rank}_pose_{sample_result.pose_rank}.pdb"
        )
        pose_file.write_text(
            "ATOM      1  C   LIG A   1       0.0   0.0   0.0  1.00  0.00           C\nEND\n"
        )

        mock_template = MagicMock()
        with (
            patch.dict("sys.modules", _mock_rdkit_numpy()),
            patch(
                "docking.tasks._parse_protein_for_mmgbsa",
                return_value={"coords": [], "charges": [], "radii": []},
            ),
            patch("docking.tasks._prepare_ligand_template", return_value=FAKE_LIGAND_TEMPLATE_DATA),
            patch("docking.tasks._compute_mmgbsa_single", return_value=-85.3),
        ):
            from rdkit import Chem

            Chem.MolFromMolFile = MagicMock(return_value=mock_template)
            _run_mmgbsa_rescoring(sample_job)

        sample_result.refresh_from_db()
        assert sample_result.mmgbsa_score == -85.3

    def test_handles_scoring_failure(self, sample_job, sample_result):
        from docking.tasks import _run_mmgbsa_rescoring

        pose_dir = sample_job.job_path / "results"
        pose_dir.mkdir(parents=True, exist_ok=True)
        pose_file = (
            pose_dir / f"pocket_{sample_result.pocket.rank}_pose_{sample_result.pose_rank}.pdb"
        )
        pose_file.write_text(
            "ATOM      1  C   LIG A   1       0.0   0.0   0.0  1.00  0.00           C\nEND\n"
        )

        mock_template = MagicMock()
        with (
            patch.dict("sys.modules", _mock_rdkit_numpy()),
            patch(
                "docking.tasks._parse_protein_for_mmgbsa",
                return_value={"coords": [], "charges": [], "radii": []},
            ),
            patch("docking.tasks._prepare_ligand_template", return_value=FAKE_LIGAND_TEMPLATE_DATA),
            patch(
                "docking.tasks._compute_mmgbsa_single",
                side_effect=RuntimeError("force field failed"),
            ),
        ):
            from rdkit import Chem

            Chem.MolFromMolFile = MagicMock(return_value=mock_template)
            _run_mmgbsa_rescoring(sample_job)

        sample_result.refresh_from_db()
        assert sample_result.mmgbsa_score is None

    def test_skips_when_ligand_sdf_unreadable(self, sample_job, sample_result):
        from docking.tasks import _run_mmgbsa_rescoring

        with (
            patch.dict("sys.modules", _mock_rdkit_numpy()),
            patch("docking.tasks._parse_protein_for_mmgbsa") as mock_parse,
        ):
            from rdkit import Chem

            Chem.MolFromMolFile = MagicMock(return_value=None)
            _run_mmgbsa_rescoring(sample_job)

        mock_parse.assert_not_called()
        sample_result.refresh_from_db()
        assert sample_result.mmgbsa_score is None

    def test_skips_when_protein_parse_fails(self, sample_job, sample_result):
        from docking.tasks import _run_mmgbsa_rescoring

        mock_template = MagicMock()
        with (
            patch.dict("sys.modules", _mock_rdkit_numpy()),
            patch("docking.tasks._parse_protein_for_mmgbsa", return_value=None),
            patch("docking.tasks._compute_mmgbsa_single") as mock_compute,
        ):
            from rdkit import Chem

            Chem.MolFromMolFile = MagicMock(return_value=mock_template)
            _run_mmgbsa_rescoring(sample_job)

        mock_compute.assert_not_called()
        sample_result.refresh_from_db()
        assert sample_result.mmgbsa_score is None

    def test_skips_when_ligand_template_prep_fails(self, sample_job, sample_result):
        from docking.tasks import _run_mmgbsa_rescoring

        mock_template = MagicMock()
        with (
            patch.dict("sys.modules", _mock_rdkit_numpy()),
            patch(
                "docking.tasks._parse_protein_for_mmgbsa",
                return_value={"coords": [], "charges": [], "radii": []},
            ),
            patch("docking.tasks._prepare_ligand_template", return_value=None),
            patch("docking.tasks._compute_mmgbsa_single") as mock_compute,
        ):
            from rdkit import Chem

            Chem.MolFromMolFile = MagicMock(return_value=mock_template)
            _run_mmgbsa_rescoring(sample_job)

        mock_compute.assert_not_called()
        sample_result.refresh_from_db()
        assert sample_result.mmgbsa_score is None


@pytest.mark.django_db
class TestComputeMMGBSASingle:
    def test_function_exists(self):
        from docking.tasks import _compute_mmgbsa_single

        assert callable(_compute_mmgbsa_single)

    def test_helper_functions_exist(self):
        from docking.tasks import _parse_ligand_pdb_coords, _prepare_ligand_template

        assert callable(_parse_ligand_pdb_coords)
        assert callable(_prepare_ligand_template)


@pytest.mark.django_db
class TestMMGBSAIntegration:
    def test_pipeline_calls_mmgbsa_when_enabled(self, sample_job):
        from docking.tasks import run_docking_pipeline

        sample_job.rescore_mmgbsa = True
        sample_job.save()

        with (
            patch("docking.tasks._run_p2rank"),
            patch("docking.tasks._run_structure_prep"),
            patch("docking.tasks._compute_admet_properties"),
            patch("docking.tasks._run_vina_docking"),
            patch("docking.tasks._run_interaction_analysis"),
            patch("docking.tasks._run_mmgbsa_rescoring") as mock_mmgbsa,
        ):
            run_docking_pipeline.run(sample_job.id)

        mock_mmgbsa.assert_called_once()

    def test_pipeline_skips_mmgbsa_when_disabled(self, sample_job):
        from docking.tasks import run_docking_pipeline

        sample_job.rescore_mmgbsa = False
        sample_job.save()

        with (
            patch("docking.tasks._run_p2rank"),
            patch("docking.tasks._run_structure_prep"),
            patch("docking.tasks._compute_admet_properties"),
            patch("docking.tasks._run_vina_docking"),
            patch("docking.tasks._run_interaction_analysis"),
            patch("docking.tasks._run_mmgbsa_rescoring") as mock_mmgbsa,
        ):
            run_docking_pipeline.run(sample_job.id)

        mock_mmgbsa.assert_not_called()


@pytest.mark.django_db
class TestMMGBSAInAPI:
    def test_results_include_mmgbsa_score(self, sample_job, sample_result):
        from django.test import Client
        from django.urls import reverse

        sample_job.status = "completed"
        sample_job.save()
        sample_result.mmgbsa_score = -72.5
        sample_result.save()

        client = Client()
        resp = client.get(reverse("docking:api_job_results", args=[sample_job.id]))
        data = resp.json()
        assert data["results"][0]["mmgbsa_score"] == -72.5

    def test_results_mmgbsa_null_when_not_computed(self, sample_job, sample_result):
        from django.test import Client
        from django.urls import reverse

        sample_job.status = "completed"
        sample_job.save()

        client = Client()
        resp = client.get(reverse("docking:api_job_results", args=[sample_job.id]))
        data = resp.json()
        assert data["results"][0]["mmgbsa_score"] is None
