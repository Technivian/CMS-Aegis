from django.db import migrations, models


def migrate_provider_response_states(apps, schema_editor):
    PlacementRequest = apps.get_model('contracts', 'PlacementRequest')
    PlacementRequest.objects.filter(provider_response_status='DECLINED').update(provider_response_status='REJECTED')
    PlacementRequest.objects.filter(provider_response_status='NO_RESPONSE').update(provider_response_status='PENDING')


class Migration(migrations.Migration):

    dependencies = [
        ('contracts', '0034_case_outcome_feedback_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='placementrequest',
            name='provider_response_deadline_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Reactiedeadline'),
        ),
        migrations.AddField(
            model_name='placementrequest',
            name='provider_response_last_reminder_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Laatste herinnering providerreactie'),
        ),
        migrations.AddField(
            model_name='placementrequest',
            name='provider_response_requested_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Aanvraag verstuurd op'),
        ),
        migrations.AlterField(
            model_name='placementrequest',
            name='provider_response_status',
            field=models.CharField(
                choices=[
                    ('PENDING', 'Nog niet vastgelegd'),
                    ('ACCEPTED', 'Geaccepteerd'),
                    ('REJECTED', 'Afgewezen'),
                    ('NEEDS_INFO', 'Aanvullende info nodig'),
                    ('WAITLIST', 'Wachtlijst'),
                    ('NO_CAPACITY', 'Geen capaciteit'),
                ],
                default='PENDING',
                max_length=20,
                verbose_name='Reactie aanbieder',
            ),
        ),
        migrations.RunPython(migrate_provider_response_states, migrations.RunPython.noop),
    ]
