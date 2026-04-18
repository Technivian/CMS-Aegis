import json

from django.core.management.base import BaseCommand
from django.utils import timezone

from contracts.models import AuditLog, Organization


class Command(BaseCommand):
    help = 'Export retention audit actions.'

    def add_arguments(self, parser):
        parser.add_argument('--organization-slug', default='')
        parser.add_argument('--output', default='')

    def handle(self, *args, **options):
        organization_slug = str(options.get('organization_slug') or '').strip()
        org = Organization.objects.filter(slug=organization_slug).first() if organization_slug else None

        audit_qs = AuditLog.objects.filter(action__in=[AuditLog.Action.EXPORT, AuditLog.Action.DELETE])
        if org is not None:
            audit_qs = audit_qs.filter(user__organization_memberships__organization=org).distinct()

        actions = [
            {
                'id': log.id,
                'action': log.action,
                'model_name': log.model_name,
                'object_id': log.object_id,
                'timestamp': log.timestamp.isoformat() if log.timestamp else None,
            }
            for log in audit_qs.order_by('-timestamp')[:250]
        ]

        payload = {
            'captured_at': timezone.now().isoformat(),
            'organization_slug': organization_slug or None,
            'action_count': len(actions),
            'actions': actions,
            'status': 'GO',
        }

        rendered = json.dumps(payload, indent=2, sort_keys=True)
        output_path = str(options.get('output') or '').strip()
        if output_path:
            with open(output_path, 'w', encoding='utf-8') as handle:
                handle.write(rendered)
                handle.write('\n')
        self.stdout.write(rendered)
