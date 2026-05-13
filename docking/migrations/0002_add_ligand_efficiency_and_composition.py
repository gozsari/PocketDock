from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("docking", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="dockingresult",
            name="ligand_efficiency",
            field=models.FloatField(
                default=0.0,
                help_text="LE = -affinity / heavy_atom_count",
            ),
        ),
        migrations.AddField(
            model_name="pocket",
            name="composition",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
