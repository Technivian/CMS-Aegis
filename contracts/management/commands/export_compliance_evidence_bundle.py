import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from contracts.services.evidence_bundle import export_evidence_bundle


class Command(BaseCommand):
    help = 'Create tamper-evident compliance evidence bundle with hash and signature.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--include',
            action='append',
            default=[],
            help='Absolute or relative file path to include. Repeat for multiple files.',
        )
        parser.add_argument('--output-dir', default='docs/evidence')
        parser.add_argument('--signing-key', default='')

    def handle(self, *args, **options):
        include_paths = list(options['include'] or [])
        if not include_paths:
            defaults = [
                'docs/RELEASE_CANDIDATE_GATE_CHECKLIST_2026-04-18.md',
                'docs/SPRINT3_BOARD_2026-04-18.md',
                'docs/SPRINT_1_2_COMPLETION_2026-04-18.md',
            ]
            include_paths = [item for item in defaults if Path(item).exists()]
        if not include_paths:
            raise CommandError('No evidence files provided. Use --include.')

        signing_key = str(options.get('signing_key') or '').strip() or str(settings.SECRET_KEY)
        try:
            result = export_evidence_bundle(
                include_paths=include_paths,
                output_dir=options['output_dir'],
                signing_key=signing_key,
            )
        except ValueError as exc:
            raise CommandError(str(exc))

        payload = {
            'status': 'exported',
            'bundle_path': str(result.bundle_path),
            'manifest_path': str(result.manifest_path),
            'sha256_path': str(result.sha256_path),
            'signature_path': str(result.signature_path),
            'files_included': result.file_count,
        }
        self.stdout.write(json.dumps(payload, indent=2, sort_keys=True))
