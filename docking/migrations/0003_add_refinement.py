from django.db import migrations, models
import django.core.validators


class Migration(migrations.Migration):

    dependencies = [
        ("docking", "0002_add_ligand_efficiency_and_composition"),
    ]

    operations = [
        migrations.AddField(
            model_name="dockingjob",
            name="refine_poses",
            field=models.BooleanField(
                default=False,
                help_text="Run OpenMM energy minimization on docked poses",
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
                    ("completed", "Completed"),
                    ("failed", "Failed"),
                ],
                default="pending",
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="dockingjob",
            name="num_pockets",
            field=models.PositiveIntegerField(
                default=3,
                help_text="Number of top pockets to dock against",
                validators=[
                    django.core.validators.MinValueValidator(1),
                    django.core.validators.MaxValueValidator(20),
                ],
            ),
        ),
        migrations.AlterField(
            model_name="dockingjob",
            name="exhaustiveness",
            field=models.PositiveIntegerField(
                default=8,
                validators=[
                    django.core.validators.MinValueValidator(1),
                    django.core.validators.MaxValueValidator(64),
                ],
            ),
        ),
    ]
