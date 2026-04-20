from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('contracts', '0015_deadline_auto_generated_deadline_generation_source'),
    ]

    operations = [
        migrations.AddField(
            model_name='duediligenceprocess',
            name='contract',
            field=models.OneToOneField(blank=True, null=True, on_delete=models.SET_NULL, related_name='due_diligence_process', to='contracts.contract'),
        ),
    ]
