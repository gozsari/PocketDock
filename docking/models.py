import uuid
from pathlib import Path

from django.db import models


def job_upload_path(instance, filename):
    return f"jobs/{instance.job_dir}/{filename}"


class DockingJob(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        RUNNING_P2RANK = "running_p2rank", "Running P2Rank"
        RUNNING_PREP = "running_prep", "Preparing Structures"
        RUNNING_VINA = "running_vina", "Running AutoDock Vina"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    name = models.CharField(max_length=255, blank=True, default="")
    job_dir = models.CharField(max_length=64, unique=True, editable=False)
    protein_file = models.FileField(upload_to=job_upload_path)
    ligand_file = models.FileField(upload_to=job_upload_path)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )
    num_pockets = models.PositiveIntegerField(
        default=3, help_text="Number of top pockets to dock against"
    )
    exhaustiveness = models.PositiveIntegerField(default=8)
    error_message = models.TextField(blank=True, default="")
    celery_task_id = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Job {self.id} - {self.name or 'Untitled'} ({self.status})"

    def save(self, *args, **kwargs):
        if not self.job_dir:
            self.job_dir = uuid.uuid4().hex[:12]
        super().save(*args, **kwargs)

    @property
    def job_path(self) -> Path:
        from django.conf import settings
        return Path(settings.MEDIA_ROOT) / "jobs" / self.job_dir

    @property
    def protein_filename(self):
        return Path(self.protein_file.name).name if self.protein_file else ""

    @property
    def ligand_filename(self):
        return Path(self.ligand_file.name).name if self.ligand_file else ""


class Pocket(models.Model):
    job = models.ForeignKey(DockingJob, on_delete=models.CASCADE, related_name="pockets")
    rank = models.PositiveIntegerField()
    score = models.FloatField(default=0.0)
    probability = models.FloatField(default=0.0)
    center_x = models.FloatField()
    center_y = models.FloatField()
    center_z = models.FloatField()
    residue_ids = models.TextField(blank=True, default="")
    surf_atom_ids = models.TextField(blank=True, default="")
    sas_points = models.PositiveIntegerField(default=0)
    composition = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["rank"]
        unique_together = [("job", "rank")]

    def __str__(self):
        return f"Pocket {self.rank} (p={self.probability:.2f}) for Job {self.job_id}"

    @property
    def center(self):
        return [self.center_x, self.center_y, self.center_z]


class DockingResult(models.Model):
    pocket = models.ForeignKey(Pocket, on_delete=models.CASCADE, related_name="results")
    pose_rank = models.PositiveIntegerField(default=1)
    affinity = models.FloatField(help_text="Binding affinity in kcal/mol (negative = better)")
    rmsd_lb = models.FloatField(default=0.0)
    rmsd_ub = models.FloatField(default=0.0)
    pose_file = models.CharField(max_length=512, blank=True, default="")
    combined_score = models.FloatField(
        default=0.0,
        help_text="Weighted combination of pocket probability and binding affinity",
    )
    ligand_efficiency = models.FloatField(
        default=0.0,
        help_text="LE = -affinity / heavy_atom_count",
    )

    class Meta:
        ordering = ["combined_score"]

    def __str__(self):
        return (
            f"Result pocket={self.pocket.rank} pose={self.pose_rank} "
            f"affinity={self.affinity:.1f} kcal/mol"
        )

    def compute_combined_score(self, w_pocket=0.4, w_affinity=0.6, max_affinity=-15.0):
        """
        Combine pocket probability with normalized affinity.
        Affinity is negative (more negative = stronger binding), so we
        normalize to 0-1 where 1 is the strongest binding.
        """
        norm_affinity = min(self.affinity, 0) / max_affinity
        norm_affinity = max(0.0, min(1.0, norm_affinity))
        self.combined_score = (w_pocket * self.pocket.probability) + (
            w_affinity * norm_affinity
        )
        return self.combined_score
