import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from contracts.services.evidence_bundle import verify_evidence_bundle


class Command(BaseCommand):
    help = 'Verify tamper-evident compliance evidence bundle integrity and signature.'

    def add_arguments(self, parser):
        parser.add_argument('--bundle-path', required=True)
        parser.add_argument('--sha256-path', default='')
        parser.add_argument('--signature-path', default='')
        parser.add_argument('--signing-key', default='')

    def handle(self, *args, **options):
        bundle_path = str(options['bundle_path']).strip()
        bundle = Path(bundle_path).expanduser().resolve()
        sha_path = str(options.get('sha256_path') or '').strip() or str(bundle.with_suffix('').with_suffix('.sha256'))
        sig_path = str(options.get('signature_path') or '').strip() or str(bundle.with_suffix('').with_suffix('.sig'))
        signing_key = str(options.get('signing_key') or '').strip() or str(settings.SECRET_KEY)

        try:
            result = verify_evidence_bundle(
                bundle_path=bundle_path,
                sha256_path=sha_path,
                signature_path=sig_path,
                signing_key=signing_key,
            )
        except ValueError as exc:
            raise CommandError(str(exc))

        self.stdout.write(json.dumps(result, indent=2, sort_keys=True))
