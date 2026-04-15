from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('contracts', '0033_region_remove_approvalrequest_assigned_to_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='caseintakeprocess',
            name='intake_outcome_notes',
            field=models.TextField(blank=True, verbose_name='Notities intake-uitkomst'),
        ),
        migrations.AddField(
            model_name='caseintakeprocess',
            name='intake_outcome_reason_code',
            field=models.CharField(
                choices=[
                    ('NONE', 'Geen specifieke reden'),
                    ('CAPACITY', 'Capaciteit'),
                    ('WAITLIST', 'Wachtlijst'),
                    ('CLIENT_DECLINED', 'Client heeft afgezien'),
                    ('PROVIDER_DECLINED', 'Aanbieder heeft afgewezen'),
                    ('NO_SHOW', 'Niet verschenen'),
                    ('NO_RESPONSE', 'Geen reactie'),
                    ('CARE_MISMATCH', 'Zorgvraag past niet'),
                    ('REGION_MISMATCH', 'Regio past niet'),
                    ('SAFETY_RISK', 'Veiligheidsrisico'),
                    ('ADMINISTRATIVE_BLOCK', 'Administratieve blokkade'),
                    ('OTHER', 'Anders'),
                ],
                default='NONE',
                max_length=30,
                verbose_name='Redencode intake-uitkomst',
            ),
        ),
        migrations.AddField(
            model_name='caseintakeprocess',
            name='intake_outcome_recorded_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Intake-uitkomst vastgelegd op'),
        ),
        migrations.AddField(
            model_name='caseintakeprocess',
            name='intake_outcome_recorded_by',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='recorded_intake_outcomes',
                to=settings.AUTH_USER_MODEL,
                verbose_name='Intake-uitkomst vastgelegd door',
            ),
        ),
        migrations.AddField(
            model_name='caseintakeprocess',
            name='intake_outcome_status',
            field=models.CharField(
                choices=[
                    ('PENDING', 'Nog niet vastgelegd'),
                    ('COMPLETED', 'Afgerond'),
                    ('CANCELLED', 'Geannuleerd'),
                    ('NO_SHOW', 'Niet verschenen'),
                ],
                default='PENDING',
                max_length=20,
                verbose_name='Uitkomst intake',
            ),
        ),
        migrations.AddField(
            model_name='placementrequest',
            name='placement_quality_notes',
            field=models.TextField(blank=True, verbose_name='Notities plaatsingskwaliteit'),
        ),
        migrations.AddField(
            model_name='placementrequest',
            name='placement_quality_reason_code',
            field=models.CharField(
                choices=[
                    ('NONE', 'Geen specifieke reden'),
                    ('CAPACITY', 'Capaciteit'),
                    ('WAITLIST', 'Wachtlijst'),
                    ('CLIENT_DECLINED', 'Client heeft afgezien'),
                    ('PROVIDER_DECLINED', 'Aanbieder heeft afgewezen'),
                    ('NO_SHOW', 'Niet verschenen'),
                    ('NO_RESPONSE', 'Geen reactie'),
                    ('CARE_MISMATCH', 'Zorgvraag past niet'),
                    ('REGION_MISMATCH', 'Regio past niet'),
                    ('SAFETY_RISK', 'Veiligheidsrisico'),
                    ('ADMINISTRATIVE_BLOCK', 'Administratieve blokkade'),
                    ('OTHER', 'Anders'),
                ],
                default='NONE',
                max_length=30,
                verbose_name='Redencode plaatsingskwaliteit',
            ),
        ),
        migrations.AddField(
            model_name='placementrequest',
            name='placement_quality_recorded_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Plaatsingskwaliteit vastgelegd op'),
        ),
        migrations.AddField(
            model_name='placementrequest',
            name='placement_quality_recorded_by',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='recorded_placement_quality_updates',
                to=settings.AUTH_USER_MODEL,
                verbose_name='Plaatsingskwaliteit vastgelegd door',
            ),
        ),
        migrations.AddField(
            model_name='placementrequest',
            name='placement_quality_status',
            field=models.CharField(
                choices=[
                    ('PENDING', 'Nog niet vastgelegd'),
                    ('GOOD_FIT', 'Goede plaatsing'),
                    ('AT_RISK', 'Risico op uitval'),
                    ('BROKEN_DOWN', 'Plaatsing vastgelopen'),
                ],
                default='PENDING',
                max_length=20,
                verbose_name='Plaatsingskwaliteit',
            ),
        ),
        migrations.AddField(
            model_name='placementrequest',
            name='provider_response_notes',
            field=models.TextField(blank=True, verbose_name='Notities reactie aanbieder'),
        ),
        migrations.AddField(
            model_name='placementrequest',
            name='provider_response_reason_code',
            field=models.CharField(
                choices=[
                    ('NONE', 'Geen specifieke reden'),
                    ('CAPACITY', 'Capaciteit'),
                    ('WAITLIST', 'Wachtlijst'),
                    ('CLIENT_DECLINED', 'Client heeft afgezien'),
                    ('PROVIDER_DECLINED', 'Aanbieder heeft afgewezen'),
                    ('NO_SHOW', 'Niet verschenen'),
                    ('NO_RESPONSE', 'Geen reactie'),
                    ('CARE_MISMATCH', 'Zorgvraag past niet'),
                    ('REGION_MISMATCH', 'Regio past niet'),
                    ('SAFETY_RISK', 'Veiligheidsrisico'),
                    ('ADMINISTRATIVE_BLOCK', 'Administratieve blokkade'),
                    ('OTHER', 'Anders'),
                ],
                default='NONE',
                max_length=30,
                verbose_name='Redencode reactie aanbieder',
            ),
        ),
        migrations.AddField(
            model_name='placementrequest',
            name='provider_response_recorded_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Reactie vastgelegd op'),
        ),
        migrations.AddField(
            model_name='placementrequest',
            name='provider_response_recorded_by',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='recorded_provider_responses',
                to=settings.AUTH_USER_MODEL,
                verbose_name='Reactie vastgelegd door',
            ),
        ),
        migrations.AddField(
            model_name='placementrequest',
            name='provider_response_status',
            field=models.CharField(
                choices=[
                    ('PENDING', 'Nog niet vastgelegd'),
                    ('ACCEPTED', 'Geaccepteerd'),
                    ('DECLINED', 'Afgewezen'),
                    ('NO_RESPONSE', 'Geen reactie'),
                ],
                default='PENDING',
                max_length=20,
                verbose_name='Reactie aanbieder',
            ),
        ),
    ]