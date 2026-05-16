import pytest

from docking.models import DockingJob, DockingResult, Pocket


@pytest.mark.django_db
class TestDockingJob:
    def test_job_dir_auto_generated(self, sample_job):
        assert sample_job.job_dir
        assert len(sample_job.job_dir) == 12

    def test_status_default(self, sample_job):
        assert sample_job.status == DockingJob.Status.PENDING

    def test_str(self, sample_job):
        s = str(sample_job)
        assert "Test Job" in s
        assert "pending" in s


@pytest.mark.django_db
class TestPocket:
    def test_center_property(self, sample_pocket):
        assert sample_pocket.center == [10.0, 20.0, 30.0]

    def test_unique_together(self, sample_job, sample_pocket):
        from django.db import IntegrityError

        with pytest.raises(IntegrityError):
            Pocket.objects.create(
                job=sample_job, rank=1, score=5.0, probability=0.5,
                center_x=0, center_y=0, center_z=0,
            )


@pytest.mark.django_db
class TestDockingResult:
    def test_combined_score_computation(self, sample_result):
        assert sample_result.combined_score > 0

    def test_combined_score_zero_affinity(self, sample_pocket):
        dr = DockingResult.objects.create(
            pocket=sample_pocket, pose_rank=2, affinity=0.0,
        )
        score = dr.compute_combined_score()
        assert score == pytest.approx(0.4 * sample_pocket.probability)

    def test_combined_score_very_strong(self, sample_pocket):
        dr = DockingResult.objects.create(
            pocket=sample_pocket, pose_rank=3, affinity=-15.0,
        )
        score = dr.compute_combined_score()
        expected = 0.4 * sample_pocket.probability + 0.6 * 1.0
        assert score == pytest.approx(expected)
