from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('contracts', '0026_webhook_endpoint_and_delivery'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='ExecutiveDashboardPreset',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=120)),
                ('filters', models.JSONField(blank=True, default=dict)),
                ('layout', models.JSONField(blank=True, default=dict)),
                ('is_shared', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='executive_dashboard_presets', to=settings.AUTH_USER_MODEL)),
                ('organization', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='executive_dashboard_presets', to='contracts.organization')),
            ],
            options={
                'ordering': ['organization__name', 'name'],
                'unique_together': {('organization', 'name')},
            },
        ),
    ]
