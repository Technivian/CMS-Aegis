import json
from datetime import timedelta
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from contracts.models import AuditLog, Organization


class Command(BaseCommand):
    help = 'Export retention execution audit actions with traceable IDs.'

    def add_arguments(self, parser):
        parser.add_argument('--organization-slug', default='')
        parser.add_argument('--days', type=int, default=30)
        parser.add_argument('--output', default='')

    def handle(self, *args, **options):
        days = max(1, int(options['days']))
        org_slug = str(options.get('organization_slug') or '').strip()
        org = None
        if org_slug:
            org = Organization.objects.filter(slug=org_slug).first()
            if org is None:
                raise CommandError('Organization not found.')

        since = timezone.now() - timedelta(days=days)
        qs = AuditLog.objects.filter(
            model_name='RetentionExecution',
            timestamp__gte=since,
        ).order_by('-timestamp')
        if org is not None:
            qs = qs.filter(changes__organization_id=org.id)

        actions = []
        for entry in qs:
            changes = entry.changes or {}
            actions.append(
                {
                    'audit_log_id': entry.id,
                    'timestamp': entry.timestamp.isoformat() if entry.timestamp else None,
                    'contract_id': changes.get('contract_id'),
                    'policy_id': changes.get('policy_id'),
                    'organization_id': changes.get('organization_id'),
                    'trace_id': changes.get('trace_id'),
                    'dry_run': changes.get('dry_run'),
                }
            )

        payload = {
            'captured_at': timezone.now().isoformat(),
            'window_days': days,
            'organization_slug': org_slug or None,
            'count': len(actions),
            'actions': actions,
        }
        rendered = json.dumps(payload, indent=2, sort_keys=True)

        output_path = str(options.get('output') or '').strip()
        if output_path:
            target = Path(output_path)
            if target.parent and not target.parent.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(rendered + '\n', encoding='utf-8')

        self.stdout.write(rendered)
