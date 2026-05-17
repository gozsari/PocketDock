import pytest

from docking.models import DockingJob, DockingResult, Pocket


@pytest.mark.django_db
class TestDockingJob:
    def test_job_dir_auto_generated(self, sample_job):
        assert sample_job.job_dir
        assert len(sample_job.job_dir) == 12

    def test_status_default(self, sample_job):
        assert sample_job.status == DockingJob.Status.PENDING

    def test_scoring_function_default(self, sample_job):
        assert sample_job.scoring_function == DockingJob.ScoringFunction.VINA

    def test_scoring_function_vinardo(self, sample_job):
        sample_job.scoring_function = DockingJob.ScoringFunction.VINARDO
        sample_job.save()
        sample_job.refresh_from_db()
        assert sample_job.scoring_function == "vinardo"
        assert sample_job.get_scoring_function_display() == "Vinardo"

    def test_admet_properties_default(self, sample_job):
        assert sample_job.admet_properties == {}

    def test_admet_properties_roundtrip(self, sample_job):
        sample_job.admet_properties = {"molecular_weight": 180.16, "lipinski_pass": True}
        sample_job.save()
        sample_job.refresh_from_db()
        assert sample_job.admet_properties["molecular_weight"] == 180.16
        assert sample_job.admet_properties["lipinski_pass"] is True

    def test_rescore_mmgbsa_default(self, sample_job):
        assert sample_job.rescore_mmgbsa is False

    def test_rescore_mmgbsa_roundtrip(self, sample_job):
        sample_job.rescore_mmgbsa = True
        sample_job.save()
        sample_job.refresh_from_db()
        assert sample_job.rescore_mmgbsa is True

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

    def test_mmgbsa_score_default_null(self, sample_result):
        assert sample_result.mmgbsa_score is None

    def test_mmgbsa_score_roundtrip(self, sample_result):
        sample_result.mmgbsa_score = -85.3
        sample_result.save()
        sample_result.refresh_from_db()
        assert sample_result.mmgbsa_score == pytest.approx(-85.3)
