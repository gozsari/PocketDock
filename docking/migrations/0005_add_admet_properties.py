from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("docking", "0004_add_scoring_function"),
    ]

    operations = [
        migrations.AddField(
            model_name="dockingjob",
            name="admet_properties",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text="Computed ADMET/drug-likeness properties from RDKit",
            ),
        ),
    ]
