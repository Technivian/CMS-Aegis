from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('contracts', '0012_organization_session_idle_timeout_minutes'),
    ]

    operations = [
        migrations.AddField(
            model_name='organization',
            name='identity_provider',
            field=models.CharField(choices=[('OIDC', 'OpenID Connect'), ('SAML', 'SAML')], default='OIDC', max_length=20),
        ),
        migrations.AddField(
            model_name='organization',
            name='saml_entity_id',
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name='organization',
            name='saml_metadata_url',
            field=models.URLField(blank=True),
        ),
        migrations.AddField(
            model_name='organization',
            name='saml_sso_url',
            field=models.URLField(blank=True),
        ),
        migrations.AddField(
            model_name='organization',
            name='saml_x509_certificate',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='organization',
            name='scim_enabled',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='organization',
            name='scim_token_created_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='organization',
            name='scim_token_hash',
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.AddField(
            model_name='organization',
            name='scim_token_last4',
            field=models.CharField(blank=True, max_length=4),
        ),
    ]
