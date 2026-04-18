import json
import uuid
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from contracts.models import AuditLog, Contract, Organization, RetentionPolicy


class Command(BaseCommand):
    help = 'Execute retention policies and archive eligible contracts with immutable audit logs.'

    def add_arguments(self, parser):
        parser.add_argument('--organization-slug', default='')
        parser.add_argument('--dry-run', action='store_true', default=False)
        parser.add_argument('--limit', type=int, default=500)

    def handle(self, *args, **options):
        dry_run = bool(options['dry_run'])
        limit = max(1, int(options['limit']))
        org_slug = str(options.get('organization_slug') or '').strip()

        organizations = Organization.objects.all().order_by('id')
        if org_slug:
            organizations = organizations.filter(slug=org_slug)

        summary = {
            'captured_at': timezone.now().isoformat(),
            'dry_run': dry_run,
            'organizations_scanned': 0,
            'policies_scanned': 0,
            'contracts_evaluated': 0,
            'contracts_archived': 0,
            'audit_entries_created': 0,
            'actions': [],
        }

        for organization in organizations:
            summary['organizations_scanned'] += 1
            policies = RetentionPolicy.objects.filter(
                organization=organization,
                is_active=True,
                category=RetentionPolicy.Category.CONTRACTS,
            ).order_by('id')
            for policy in policies:
                summary['policies_scanned'] += 1
                cutoff_date = timezone.now().date() - timedelta(days=policy.retention_period_days)
                candidates = Contract.objects.filter(
                    organization=organization,
                    end_date__isnull=False,
                    end_date__lte=cutoff_date,
                ).exclude(lifecycle_stage='ARCHIVED').order_by('id')[:limit]
                for contract in candidates:
                    summary['contracts_evaluated'] += 1
                    trace_id = str(uuid.uuid4())
                    action_payload = {
                        'trace_id': trace_id,
                        'organization_id': organization.id,
                        'policy_id': policy.id,
                        'contract_id': contract.id,
                        'retention_period_days': policy.retention_period_days,
                        'cutoff_date': cutoff_date.isoformat(),
                        'dry_run': dry_run,
                    }
                    if not dry_run:
                        contract.lifecycle_stage = 'ARCHIVED'
                        contract.save(update_fields=['lifecycle_stage', 'updated_at'])
                        AuditLog.objects.create(
                            action=AuditLog.Action.UPDATE,
                            model_name='RetentionExecution',
                            object_id=contract.id,
                            object_repr=contract.title[:300],
                            changes=action_payload,
                        )
                        summary['contracts_archived'] += 1
                        summary['audit_entries_created'] += 1
                    summary['actions'].append(action_payload)

        self.stdout.write(json.dumps(summary, indent=2, sort_keys=True))
