from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("docking", "0005_add_admet_properties"),
    ]

    operations = [
        migrations.AddField(
            model_name="dockingjob",
            name="rescore_mmgbsa",
            field=models.BooleanField(
                default=False,
                help_text="Compute MM-GBSA binding free energy for each pose",
            ),
        ),
        migrations.AddField(
            model_name="dockingresult",
            name="mmgbsa_score",
            field=models.FloatField(
                blank=True,
                null=True,
                help_text="MM-GBSA binding free energy in kJ/mol (more negative = stronger)",
            ),
        ),
        migrations.AlterField(
            model_name="dockingjob",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
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
