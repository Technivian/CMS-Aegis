import hashlib
import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone


class Command(BaseCommand):
    help = 'Verify compliance evidence bundle integrity.'

    def add_arguments(self, parser):
        parser.add_argument('--bundle-path', required=True)
        parser.add_argument('--sha256-path', required=True)
        parser.add_argument('--signature-path', required=True)

    def handle(self, *args, **options):
        bundle_path = Path(options['bundle_path']).resolve()
        sha_path = Path(options['sha256_path']).resolve()
        sig_path = Path(options['signature_path']).resolve()

        for path in (bundle_path, sha_path, sig_path):
            if not path.exists():
                raise CommandError(f'Missing verification input: {path}')

        expected_hash = sha_path.read_text(encoding='utf-8').split()[0].strip()
        actual_hash = hashlib.sha256(bundle_path.read_bytes()).hexdigest()
        hash_match = bool(expected_hash) and expected_hash == actual_hash

        signature_marker = sig_path.read_text(encoding='utf-8').strip()
        signature_present = bool(signature_marker)

        status = 'VERIFIED' if hash_match and signature_present else 'FAILED'
        payload = {
            'captured_at': timezone.now().isoformat(),
            'bundle_path': str(bundle_path),
            'hash_match': hash_match,
            'signature_present': signature_present,
            'status': status,
        }
        self.stdout.write(json.dumps(payload, indent=2, sort_keys=True))

        if status != 'VERIFIED':
            raise CommandError('Compliance evidence bundle verification failed.')
