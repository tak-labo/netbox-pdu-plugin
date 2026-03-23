from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("netbox_pdu_plugin", "0004_pduoutlet_apparent_power_va"),
    ]

    operations = [
        migrations.AddField(
            model_name="managedpdu",
            name="metrics_status",
            field=models.CharField(
                choices=[
                    ("success", "Success"),
                    ("failed", "Failed"),
                    ("never", "Never synced"),
                ],
                default="never",
                max_length=30,
                verbose_name="Metrics Status",
            ),
        ),
    ]
