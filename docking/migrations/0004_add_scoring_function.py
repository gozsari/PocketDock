from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("docking", "0003_add_refinement"),
    ]

    operations = [
        migrations.AddField(
            model_name="dockingjob",
            name="scoring_function",
            field=models.CharField(
                choices=[("vina", "Vina"), ("vinardo", "Vinardo")],
                default="vina",
                help_text="Scoring function for AutoDock Vina",
                max_length=10,
            ),
        ),
    ]
