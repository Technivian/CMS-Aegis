from django.db import migrations, models
from django.core.validators import MinValueValidator


class Migration(migrations.Migration):
    dependencies = [
        ('contracts', '0011_organization_require_mfa_userprofile_mfa_enabled_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='organization',
            name='session_idle_timeout_minutes',
            field=models.PositiveIntegerField(default=120, validators=[MinValueValidator(5)]),
        ),
    ]
