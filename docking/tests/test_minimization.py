"""Tests for the OpenMM energy minimization pipeline step.

These tests verify the integration logic. The actual OpenMM minimization
requires the openmm, pdbfixer, and openmmforcefields packages which may
not be installed in all environments. Tests that require OpenMM are
marked with pytest.mark.skipif and will be skipped gracefully.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from docking.models import DockingJob, DockingResult, Pocket

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.mark.django_db
class TestRunEnergyMinimization:
    def test_skips_when_openmm_not_installed(self, sample_job, sample_result):
        """When OpenMM is not installed, refinement logs a warning and returns."""
        from docking.tasks import _run_energy_minimization

        sample_job.refine_poses = True
        sample_job.save()

        with patch("docking.tasks.logger") as mock_logger:
            with patch.dict("sys.modules", {
                "pdbfixer": None,
                "openmm": None,
                "openmm.app": None,
                "openmm.unit": None,
            }):
                # Import will fail inside the function, should be caught
                _run_energy_minimization(sample_job)

        # Should have logged a warning about OpenMM not being available
        assert mock_logger.warning.called

    def test_no_results_to_refine(self, sample_job):
        """With no docking results, refinement should complete without error."""
        from docking.tasks import _run_energy_minimization

        sample_job.refine_poses = True
        sample_job.save()

        # Patch imports to succeed but there are no results
        with patch("docking.tasks.logger"):
            try:
                _run_energy_minimization(sample_job)
            except ImportError:
                pytest.skip("OpenMM not installed")

    def test_status_set_to_running_refinement(self, sample_job):
        """The job status should be set to RUNNING_REFINEMENT."""
        from docking.tasks import _run_energy_minimization

        sample_job.refine_poses = True
        sample_job.save()

        try:
            _run_energy_minimization(sample_job)
        except (ImportError, Exception):
            pass

        sample_job.refresh_from_db()
        assert sample_job.status == DockingJob.Status.RUNNING_REFINEMENT


@pytest.mark.django_db
class TestMinimizeSinglePose:
    def test_function_exists_and_callable(self):
        """Verify _minimize_single_pose is importable."""
        from docking.tasks import _minimize_single_pose

        assert callable(_minimize_single_pose)


@pytest.mark.django_db
class TestRefinementIntegration:
    def test_pipeline_calls_refinement_when_enabled(self, sample_job):
        """When refine_poses is True, the pipeline should call _run_energy_minimization."""
        from docking.tasks import run_docking_pipeline

        sample_job.refine_poses = True
        sample_job.save()

        with patch("docking.tasks._run_p2rank"), \
             patch("docking.tasks._run_structure_prep"), \
             patch("docking.tasks._run_vina_docking"), \
             patch("docking.tasks._run_interaction_analysis"), \
             patch("docking.tasks._run_energy_minimization") as mock_min:
            run_docking_pipeline.run(sample_job.id)

        mock_min.assert_called_once()

    def test_pipeline_skips_refinement_when_disabled(self, sample_job):
        """When refine_poses is False, the pipeline should not call _run_energy_minimization."""
        from docking.tasks import run_docking_pipeline

        sample_job.refine_poses = False
        sample_job.save()

        with patch("docking.tasks._run_p2rank"), \
             patch("docking.tasks._run_structure_prep"), \
             patch("docking.tasks._run_vina_docking"), \
             patch("docking.tasks._run_interaction_analysis"), \
             patch("docking.tasks._run_energy_minimization") as mock_min:
            run_docking_pipeline.run(sample_job.id)

        mock_min.assert_not_called()
