import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from contracts.models import Organization
from contracts.services.executive_analytics import build_executive_analytics_snapshot


class Command(BaseCommand):
    help = 'Generate multi-organization executive analytics evidence snapshot.'

    def add_arguments(self, parser):
        parser.add_argument('--organization-slug', action='append', default=[])
        parser.add_argument('--output', default='')

    def handle(self, *args, **options):
        requested_slugs = [str(slug).strip() for slug in (options.get('organization_slug') or []) if str(slug).strip()]
        organizations = Organization.objects.all().order_by('slug')
        if requested_slugs:
            organizations = organizations.filter(slug__in=requested_slugs)
            found = set(organizations.values_list('slug', flat=True))
            missing = [slug for slug in requested_slugs if slug not in found]
            if missing:
                raise CommandError(f'Unknown organization slug(s): {", ".join(missing)}')

        payload = {
            'captured_at': timezone.now().isoformat(),
            'organization_count': organizations.count(),
            'snapshots': [build_executive_analytics_snapshot(org) for org in organizations],
        }

        rendered = json.dumps(payload, indent=2, sort_keys=True)
        output_path = str(options.get('output') or '').strip()
        if output_path:
            target = Path(output_path)
            if target.parent and not target.parent.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(rendered + '\n', encoding='utf-8')
        self.stdout.write(rendered)
