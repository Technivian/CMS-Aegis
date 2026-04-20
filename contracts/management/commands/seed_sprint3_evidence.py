from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from contracts.models import (
    AuditLog,
    Contract,
    Organization,
    OrganizationMembership,
    SalesforceSyncRun,
    SignatureRequest,
    WebhookDelivery,
    WebhookEndpoint,
)


User = get_user_model()


class Command(BaseCommand):
    help = 'Seed synthetic Sprint 3 evidence records for release-gate workflows.'

    def add_arguments(self, parser):
        parser.add_argument('--organization-slug', default='demo-firm')
        parser.add_argument('--organization-name', default='Demo Firm')

    def handle(self, *args, **options):
        now = timezone.now()
        organization_slug = str(options.get('organization_slug') or 'demo-firm').strip() or 'demo-firm'
        organization_name = str(options.get('organization_name') or 'Demo Firm').strip() or 'Demo Firm'

        admin = User.objects.filter(username='admin').first()
        if admin is None:
            admin = User.objects.create_superuser(
                username='admin',
                email='admin@example.com',
                password='admin123',
                first_name='Admin',
                last_name='User',
            )

        organization, _ = Organization.objects.get_or_create(
            slug=organization_slug,
            defaults={'name': organization_name},
        )
        if organization.name != organization_name:
            organization.name = organization_name
            organization.save(update_fields=['name'])

        OrganizationMembership.objects.get_or_create(
            organization=organization,
            user=admin,
            defaults={
                'role': OrganizationMembership.Role.OWNER,
                'is_active': True,
            },
        )

        contract = Contract.objects.filter(
            organization=organization,
            title='Sprint 3 Evidence Contract',
        ).first()
        if contract is None:
            contract = Contract.objects.create(
                organization=organization,
                title='Sprint 3 Evidence Contract',
                contract_type=Contract.ContractType.MSA,
                content='Synthetic evidence contract used for release-gate verification.',
                status=Contract.Status.ACTIVE,
                counterparty='Evidence Counterparty LLC',
                value=250000,
                currency=Contract.Currency.USD,
                governing_law='State of Delaware',
                jurisdiction='New York',
                start_date=now.date() - timedelta(days=30),
                end_date=now.date() + timedelta(days=335),
                lifecycle_stage='EXECUTED',
                created_by=admin,
            )

        sync_run = SalesforceSyncRun.objects.filter(
            organization=organization,
            status=SalesforceSyncRun.Status.SUCCESS,
            completed_at__gte=now - timedelta(days=7),
            created_count__gt=0,
        ).first()
        if sync_run is None:
            sync_run = SalesforceSyncRun.objects.create(
                organization=organization,
                connection=None,
                triggered_by=admin,
                trigger_source=SalesforceSyncRun.TriggerSource.COMMAND,
                status=SalesforceSyncRun.Status.SUCCESS,
                dry_run=False,
                limit_applied=200,
                source_object='Opportunity',
                fetched_records=1,
                created_count=1,
                updated_count=0,
                skipped_count=0,
                error_count=0,
                summary={
                    'created': 1,
                    'updated': 0,
                    'skipped': 0,
                    'errors': [],
                    'source_object': 'Opportunity',
                },
                completed_at=now,
            )

        endpoint = WebhookEndpoint.objects.filter(
            organization=organization,
            name='Sprint 3 Evidence Endpoint',
        ).first()
        if endpoint is None:
            endpoint = WebhookEndpoint.objects.create(
                organization=organization,
                name='Sprint 3 Evidence Endpoint',
                url='https://example.com/webhooks/sprint3-evidence',
                secret='synthetic-evidence-secret',
                event_types=['salesforce.sync.completed', 'contract.signed'],
                status=WebhookEndpoint.Status.ACTIVE,
                max_attempts=5,
                created_by=admin,
            )

        if WebhookDelivery.objects.filter(
            organization=organization,
            endpoint=endpoint,
            event_type='salesforce.sync.completed',
            status=WebhookDelivery.Status.SENT,
            created_at__gte=now - timedelta(days=7),
        ).first() is None:
            WebhookDelivery.objects.create(
                organization=organization,
                endpoint=endpoint,
                event_type='salesforce.sync.completed',
                payload={
                    'run_id': sync_run.id,
                    'status': sync_run.status,
                },
                status=WebhookDelivery.Status.SENT,
                attempt_count=1,
                max_attempts=5,
                response_status=200,
                response_body='OK',
                sent_at=now,
            )

        signature_request = SignatureRequest.objects.filter(
            organization=organization,
            contract=contract,
            signer_email='signer@example.com',
        ).first()
        if signature_request is None:
            signature_request = SignatureRequest.objects.create(
                organization=organization,
                contract=contract,
                signer_name='Evidence Signer',
                signer_email='signer@example.com',
                signer_role='Authorized Signatory',
                status=SignatureRequest.Status.SIGNED,
                external_id='synth-esign-001',
                sent_at=now - timedelta(hours=2),
                viewed_at=now - timedelta(hours=1, minutes=30),
                signed_at=now - timedelta(hours=1),
                created_by=admin,
            )

        if AuditLog.objects.filter(
            model_name='ESignEvent',
            object_id=signature_request.id,
            changes__applied=True,
        ).first() is None:
            AuditLog.objects.create(
                user=admin,
                action=AuditLog.Action.UPDATE,
                model_name='ESignEvent',
                object_id=signature_request.id,
                object_repr=str(signature_request),
                changes={
                    'applied': True,
                    'dry_run': False,
                    'event_id': 'synth-esign-event-001',
                    'to_status': SignatureRequest.Status.SIGNED,
                },
            )

        self.stdout.write(self.style.SUCCESS('Sprint 3 evidence seeded successfully.'))
        self.stdout.write(f'  Organization: {organization.slug}')
        self.stdout.write(f'  Salesforce sync run: {sync_run.id}')
        self.stdout.write(f'  Signature request: {signature_request.id}')
