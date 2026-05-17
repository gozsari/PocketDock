from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("docking", "0007_add_batch_docking"),
    ]

    operations = [
        migrations.AddField(
            model_name="dockingjob",
            name="ensemble_id",
            field=models.CharField(
                blank=True, db_index=True, default="",
                help_text="Shared ID linking jobs in the same ensemble run",
                max_length=64,
            ),
        ),
        migrations.AddField(
            model_name="dockingjob",
            name="ensemble_method",
            field=models.CharField(
                choices=[
                    ("none", "None"),
                    ("nma", "Normal Mode Analysis"),
                    ("md", "Brief MD Simulation"),
                ],
                default="none",
                help_text="Method used to generate receptor conformations",
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name="dockingjob",
            name="conformation_index",
            field=models.PositiveIntegerField(
                default=0,
                help_text="0 = parent/original, 1..N = generated conformation",
            ),
        ),
        migrations.AddField(
            model_name="dockingjob",
            name="num_conformations",
            field=models.PositiveIntegerField(
                default=5,
                help_text="Number of receptor conformations to generate",
            ),
        ),
        migrations.AlterField(
            model_name="dockingjob",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
                    ("running_ensemble", "Generating Conformations"),
                    ("running_p2rank", "Running P2Rank"),
                    ("running_prep", "Preparing Structures"),
                    ("running_vina", "Running AutoDock Vina"),
                    ("running_refinement", "Refining Poses"),
                    ("running_mmgbsa", "Computing MM-GBSA"),
                    ("completed", "Completed"),
                    ("failed", "Failed"),
                ],
                default="pending",
                max_length=20,
            ),
        ),
    ]
