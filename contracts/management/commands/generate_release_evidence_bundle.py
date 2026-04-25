import json
from pathlib import Path

from django.core.management import BaseCommand, call_command, CommandError
from django.utils import timezone


class Command(BaseCommand):
    help = 'Generate Sprint 3 release evidence artifacts and a summary bundle.'

    def add_arguments(self, parser):
        parser.add_argument('--organization-slug', default='demo-firm')
        parser.add_argument('--organization-name', default='Demo Firm')
        parser.add_argument('--output-dir', default='docs/evidence/release-bundle')
        parser.add_argument(
            '--skip-seed',
            action='store_true',
            help='Do not seed synthetic Sprint 3 evidence before running reports.',
        )
        parser.add_argument(
            '--require-dead-letter-evidence',
            action='store_true',
            help='Require dead-letter webhook evidence in the integration report.',
        )
        parser.add_argument(
            '--fail-on-no-go',
            action='store_true',
            help='Exit with a non-zero status if any report is NO-GO.',
        )

    def _run_report(self, command_name, **kwargs):
        output = kwargs.pop('output', None)
        rendered = []

        class _Capture:
            def write(self, value):
                rendered.append(str(value))

        call_command(command_name, stdout=_Capture(), **kwargs)
        payload = json.loads(''.join(rendered))
        if output:
            output.write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n', encoding='utf-8')
        return payload

    def handle(self, *args, **options):
        output_dir = Path(options['output_dir'])
        output_dir.mkdir(parents=True, exist_ok=True)

        if not options['skip_seed']:
            call_command(
                'seed_sprint3_evidence',
                organization_slug=options['organization_slug'],
                organization_name=options['organization_name'],
            )

        release_gate_path = output_dir / 'release-gate-report.json'
        sprint3_integration_path = output_dir / 'sprint3-integration-report.json'
        esign_integration_path = output_dir / 'esign-integration-report.json'

        release_gate = self._run_report('generate_release_gate_report', output=release_gate_path)
        sprint3_integration = self._run_report(
            'generate_sprint3_integration_report',
            output=sprint3_integration_path,
            require_dead_letter_evidence=options['require_dead_letter_evidence'],
        )
        esign_integration = self._run_report(
            'generate_esign_integration_report',
            output=esign_integration_path,
            organization_slug=options['organization_slug'],
        )

        bundle = {
            'captured_at': timezone.now().isoformat(),
            'organization_slug': options['organization_slug'],
            'organization_name': options['organization_name'],
            'output_dir': str(output_dir),
            'artifacts': {
                'release_gate_report': str(release_gate_path),
                'sprint3_integration_report': str(sprint3_integration_path),
                'esign_integration_report': str(esign_integration_path),
            },
            'reports': {
                'release_gate': release_gate,
                'sprint3_integration': sprint3_integration,
                'esign_integration': esign_integration,
            },
        }
        bundle['go_no_go'] = (
            'GO'
            if release_gate.get('go_no_go') == 'GO'
            and sprint3_integration.get('status') == 'GO'
            and esign_integration.get('status') == 'GO'
            else 'NO-GO'
        )

        bundle_path = output_dir / 'release-evidence-bundle.json'
        bundle_path.write_text(json.dumps(bundle, indent=2, sort_keys=True) + '\n', encoding='utf-8')
        self.stdout.write(json.dumps(bundle, indent=2, sort_keys=True))

        if options['fail_on_no_go'] and bundle['go_no_go'] != 'GO':
            raise CommandError('Release evidence bundle is NO-GO.')
