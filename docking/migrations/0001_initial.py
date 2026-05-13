import django.db.models.deletion
from django.db import migrations, models

import docking.models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="DockingJob",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(blank=True, default="", max_length=255)),
                ("job_dir", models.CharField(editable=False, max_length=64, unique=True)),
                ("protein_file", models.FileField(upload_to=docking.models.job_upload_path)),
                ("ligand_file", models.FileField(upload_to=docking.models.job_upload_path)),
                ("status", models.CharField(choices=[("pending", "Pending"), ("running_p2rank", "Running P2Rank"), ("running_prep", "Preparing Structures"), ("running_vina", "Running AutoDock Vina"), ("completed", "Completed"), ("failed", "Failed")], default="pending", max_length=20)),
                ("num_pockets", models.PositiveIntegerField(default=3, help_text="Number of top pockets to dock against")),
                ("exhaustiveness", models.PositiveIntegerField(default=8)),
                ("error_message", models.TextField(blank=True, default="")),
                ("celery_task_id", models.CharField(blank=True, default="", max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="Pocket",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("rank", models.PositiveIntegerField()),
                ("score", models.FloatField(default=0.0)),
                ("probability", models.FloatField(default=0.0)),
                ("center_x", models.FloatField()),
                ("center_y", models.FloatField()),
                ("center_z", models.FloatField()),
                ("residue_ids", models.TextField(blank=True, default="")),
                ("surf_atom_ids", models.TextField(blank=True, default="")),
                ("sas_points", models.PositiveIntegerField(default=0)),
                ("job", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="pockets", to="docking.dockingjob")),
            ],
            options={
                "ordering": ["rank"],
                "unique_together": {("job", "rank")},
            },
        ),
        migrations.CreateModel(
            name="DockingResult",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("pose_rank", models.PositiveIntegerField(default=1)),
                ("affinity", models.FloatField(help_text="Binding affinity in kcal/mol (negative = better)")),
                ("rmsd_lb", models.FloatField(default=0.0)),
                ("rmsd_ub", models.FloatField(default=0.0)),
                ("pose_file", models.CharField(blank=True, default="", max_length=512)),
                ("combined_score", models.FloatField(default=0.0, help_text="Weighted combination of pocket probability and binding affinity")),
                ("pocket", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="results", to="docking.pocket")),
            ],
            options={
                "ordering": ["combined_score"],
            },
        ),
    ]
