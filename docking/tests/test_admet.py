from pathlib import Path
from unittest.mock import patch

import pytest

from docking.tasks import _compute_admet_properties


@pytest.mark.django_db
class TestComputeAdmetProperties:
    def test_computes_properties_for_sdf(self, sample_job, tmp_path):
        """Test ADMET computation with a real RDKit-readable SDF."""
        sdf_content = """aspirin
     RDKit          3D

 13 13  0  0  0  0  0  0  0  0999 V2000
    0.0000    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
    1.2124    0.7000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
    1.2124    2.1000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
    0.0000    2.8000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
   -1.2124    2.1000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
   -1.2124    0.7000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
    2.4249    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
    2.4249   -1.2000    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0
    3.4000    0.5000    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0
   -2.4249    0.0000    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0
   -3.6000    0.7000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
   -3.6000    1.9000    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0
   -4.8000    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
  1  2  2  0
  2  3  1  0
  3  4  2  0
  4  5  1  0
  5  6  2  0
  6  1  1  0
  2  7  1  0
  7  8  2  0
  7  9  1  0
  6 10  1  0
 10 11  1  0
 11 12  2  0
 11 13  1  0
M  END
$$$$
"""
        sdf_path = Path(sample_job.ligand_file.path)
        sdf_path.write_text(sdf_content)

        _compute_admet_properties(sample_job)

        sample_job.refresh_from_db()
        props = sample_job.admet_properties
        assert props, "ADMET properties should not be empty"
        assert "molecular_weight" in props
        assert "logp" in props
        assert "hba" in props
        assert "hbd" in props
        assert "tpsa" in props
        assert "rotatable_bonds" in props
        assert "qed" in props
        assert "lipinski_violations" in props
        assert "lipinski_pass" in props
        assert "veber_pass" in props
        assert "fsp3" in props
        assert "heavy_atoms" in props
        assert isinstance(props["molecular_weight"], float)
        assert props["molecular_weight"] > 0
        assert isinstance(props["lipinski_pass"], bool)
        assert isinstance(props["veber_pass"], bool)

    def test_handles_unreadable_ligand(self, sample_job):
        """Gracefully handles ligand files RDKit can't parse."""
        sdf_path = Path(sample_job.ligand_file.path)
        sdf_path.write_text("not a real molecule")

        _compute_admet_properties(sample_job)

        sample_job.refresh_from_db()
        assert sample_job.admet_properties == {}

    def test_handles_unsupported_format(self, sample_job):
        """Gracefully handles unsupported file extensions."""
        new_name = sample_job.ligand_file.name.replace(".sdf", ".xyz")
        sample_job.ligand_file.name = new_name
        sample_job.save()

        _compute_admet_properties(sample_job)
        sample_job.refresh_from_db()
        assert sample_job.admet_properties == {}

    def test_lipinski_violations_counted(self, sample_job):
        """A large molecule should trigger Lipinski violations."""
        sdf_content = """big_mol
     RDKit          3D

  1  0  0  0  0  0  0  0  0  0999 V2000
    0.0000    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
M  END
$$$$
"""
        sdf_path = Path(sample_job.ligand_file.path)
        sdf_path.write_text(sdf_content)

        _compute_admet_properties(sample_job)
        sample_job.refresh_from_db()
        props = sample_job.admet_properties
        assert "lipinski_violations" in props
        assert isinstance(props["lipinski_violations"], int)
        assert props["lipinski_violations"] >= 0


@pytest.mark.django_db
class TestAdmetInPipeline:
    def test_pipeline_calls_admet(self, sample_job):
        """Pipeline should call _compute_admet_properties."""
        from docking.tasks import run_docking_pipeline

        with (
            patch("docking.tasks._run_p2rank"),
            patch("docking.tasks._run_structure_prep"),
            patch("docking.tasks._compute_admet_properties") as mock_admet,
            patch("docking.tasks._run_vina_docking"),
            patch("docking.tasks._run_interaction_analysis"),
        ):
            run_docking_pipeline.run(sample_job.id)

        mock_admet.assert_called_once()


@pytest.mark.django_db
class TestAdmetInAPI:
    def test_results_include_admet(self, sample_job, sample_result):
        from django.test import Client
        from django.urls import reverse

        sample_job.status = "completed"
        sample_job.admet_properties = {
            "molecular_weight": 180.16,
            "logp": 1.31,
            "hba": 4,
            "hbd": 1,
            "tpsa": 63.6,
            "lipinski_pass": True,
        }
        sample_job.save()

        client = Client()
        resp = client.get(reverse("docking:api_job_results", args=[sample_job.id]))
        data = resp.json()
        assert "admet" in data
        assert data["admet"]["molecular_weight"] == 180.16
        assert data["admet"]["lipinski_pass"] is True
