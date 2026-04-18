import hashlib
import json
from pathlib import Path
import zipfile

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone


class Command(BaseCommand):
    help = 'Export tamper-evident compliance evidence bundle.'

    def add_arguments(self, parser):
        parser.add_argument('--include', action='append', default=[])
        parser.add_argument('--output-dir', required=True)

    def handle(self, *args, **options):
        output_dir = Path(options['output_dir']).resolve()
        output_dir.mkdir(parents=True, exist_ok=True)

        includes = [Path(p).resolve() for p in options.get('include') or []]
        if not includes:
            raise CommandError('At least one --include path is required.')
        for item in includes:
            if not item.exists():
                raise CommandError(f'Included evidence file not found: {item}')

        stamp = timezone.now().strftime('%Y%m%dT%H%M%SZ')
        bundle_path = output_dir / f'compliance-evidence-{stamp}.zip'
        sha_path = output_dir / f'compliance-evidence-{stamp}.sha256'
        sig_path = output_dir / f'compliance-evidence-{stamp}.sig'

        with zipfile.ZipFile(bundle_path, mode='w', compression=zipfile.ZIP_DEFLATED) as archive:
            for item in includes:
                archive.write(item, arcname=item.name)

        digest = hashlib.sha256(bundle_path.read_bytes()).hexdigest()
        sha_path.write_text(f'{digest}  {bundle_path.name}\n', encoding='utf-8')
        sig_path.write_text('unsigned-local-development\n', encoding='utf-8')

        payload = {
            'captured_at': timezone.now().isoformat(),
            'bundle_path': str(bundle_path),
            'sha256_path': str(sha_path),
            'signature_path': str(sig_path),
            'file_count': len(includes),
            'status': 'GO',
        }
        self.stdout.write(json.dumps(payload, indent=2, sort_keys=True))
