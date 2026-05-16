from pathlib import Path

import pytest

from docking.models import DockingJob, DockingResult, Pocket

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures_dir():
    return FIXTURES_DIR


@pytest.fixture
def sample_job(db, tmp_path):
    protein = tmp_path / "protein.pdb"
    protein.write_text("ATOM      1  N   ALA A   1       0.0   0.0   0.0  1.00  0.00           N\nEND\n")
    ligand = tmp_path / "ligand.sdf"
    ligand.write_text("\n  SDF\n\n  1  0  0  0  0  0  0  0  0  0  1 V2000\n    0.0    0.0    0.0 C   0  0\nM  END\n")

    from django.core.files.uploadedfile import SimpleUploadedFile

    job = DockingJob.objects.create(
        name="Test Job",
        protein_file=SimpleUploadedFile("protein.pdb", protein.read_bytes()),
        ligand_file=SimpleUploadedFile("ligand.sdf", ligand.read_bytes()),
        num_pockets=3,
        exhaustiveness=8,
    )
    return job


@pytest.fixture
def sample_pocket(sample_job):
    return Pocket.objects.create(
        job=sample_job,
        rank=1,
        score=12.0,
        probability=0.85,
        center_x=10.0,
        center_y=20.0,
        center_z=30.0,
        residue_ids="A_42_ALA,A_43_VAL",
    )


@pytest.fixture
def sample_result(sample_pocket):
    dr = DockingResult.objects.create(
        pocket=sample_pocket,
        pose_rank=1,
        affinity=-7.5,
        rmsd_lb=0.0,
        rmsd_ub=0.0,
        pose_file="results/pocket_1_pose_1.pdb",
        ligand_efficiency=0.35,
    )
    dr.compute_combined_score()
    dr.save(update_fields=["combined_score"])
    return dr
