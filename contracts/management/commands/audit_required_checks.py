from pathlib import Path

import yaml
from django.core.management.base import BaseCommand, CommandError


REQUIRED_CHECKS = [
    'pr-release-evidence',
    'quality-and-tenancy',
    'security-scans',
    'verify-ui',
]


class Command(BaseCommand):
    help = 'Audit required GitHub checks against workflow job names.'

    def add_arguments(self, parser):
        parser.add_argument('--json', action='store_true', help='Emit JSON output.')

    def _load_workflows(self):
        repo_root = Path(__file__).resolve().parents[3]
        workflow_dir = repo_root / '.github' / 'workflows'
        workflows = {}

        for workflow_path in sorted(workflow_dir.glob('*.yml')):
            with workflow_path.open('r', encoding='utf-8') as handle:
                workflow = yaml.safe_load(handle) or {}

            workflow_name = workflow.get('name') or workflow_path.stem
            jobs = sorted((workflow.get('jobs') or {}).keys())
            workflows[workflow_name] = {
                'path': workflow_path.name,
                'jobs': jobs,
            }

        return workflows

    def handle(self, *args, **options):
        workflows = self._load_workflows()
        job_index = {}
        for workflow_name, payload in workflows.items():
            for job_name in payload['jobs']:
                job_index.setdefault(job_name, []).append(workflow_name)

        report = {
            'required_checks': [],
            'workflows': workflows,
            'missing_checks': [],
        }

        for check_name in REQUIRED_CHECKS:
            report['required_checks'].append(
                {
                    'name': check_name,
                    'matched_workflows': job_index.get(check_name, []),
                }
            )
            if check_name not in job_index:
                report['missing_checks'].append(check_name)

        if options['json']:
            import json

            self.stdout.write(json.dumps(report, indent=2))
        else:
            self.stdout.write('Required check audit')
            self.stdout.write('--------------------')
            for entry in report['required_checks']:
                matches = entry['matched_workflows']
                status = 'OK' if matches else 'MISSING'
                self.stdout.write(f"- {entry['name']}: {status}")
                if matches:
                    self.stdout.write(f"  workflows: {', '.join(matches)}")

        if report['missing_checks']:
            missing = ', '.join(report['missing_checks'])
            raise CommandError(f'Missing required checks: {missing}')

        self.stdout.write(self.style.SUCCESS('All required checks match workflow job names.'))
