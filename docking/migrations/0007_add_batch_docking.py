from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("docking", "0006_add_mmgbsa"),
    ]

    operations = [
        migrations.AddField(
            model_name="dockingjob",
            name="batch_id",
            field=models.CharField(
                blank=True, db_index=True, default="",
                help_text="Shared ID linking jobs in the same batch submission",
                max_length=64,
            ),
        ),
        migrations.AddField(
            model_name="dockingjob",
            name="ligand_name",
            field=models.CharField(
                blank=True, default="",
                help_text="Molecule name / title for batch dashboard display",
                max_length=255,
            ),
        ),
    ]
