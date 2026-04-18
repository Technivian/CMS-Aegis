from django.core.management.base import BaseCommand, CommandError

from contracts.models import Workflow, WorkflowTemplate
from contracts.services.workflow_templates import clone_template_version, migrate_workflows_to_template


class Command(BaseCommand):
    help = 'Clone a workflow template version and optionally migrate workflows to it.'

    def add_arguments(self, parser):
        parser.add_argument('--source-template-id', type=int, required=True, help='Template to version.')
        parser.add_argument('--name', type=str, default='', help='Override the cloned template name.')
        parser.add_argument('--description', type=str, default='', help='Override the cloned template description.')
        parser.add_argument('--category', type=str, default='', help='Override the cloned template category.')
        parser.add_argument('--workflow-ids', type=str, default='', help='Comma-separated workflow ids to migrate.')
        parser.add_argument('--migrate-workflows', action='store_true', help='Move matching workflows to the new version.')
        parser.add_argument('--deactivate-source', action='store_true', help='Deactivate the source template after cloning.')

    def handle(self, *args, **options):
        source_template = WorkflowTemplate.objects.filter(pk=options['source_template_id']).first()
        if not source_template:
            raise CommandError(f"WorkflowTemplate {options['source_template_id']} not found.")

        cloned_template = clone_template_version(
            source_template,
            name=options['name'].strip() or None,
            description=options['description'].strip() or None,
            category=options['category'].strip() or None,
        )

        migration_result = None
        if options['migrate_workflows']:
            try:
                workflow_ids = [
                    int(value.strip())
                    for value in options['workflow_ids'].split(',')
                    if value.strip()
                ]
            except ValueError as exc:
                raise CommandError('workflow-ids must be a comma-separated list of integers.') from exc
            workflows = Workflow.objects.filter(template=source_template)
            if workflow_ids:
                workflows = workflows.filter(pk__in=workflow_ids)
            migration_result = migrate_workflows_to_template(
                source_template,
                cloned_template,
                workflows=workflows,
            )

        if options['deactivate_source']:
            source_template.is_active = False
            source_template.save(update_fields=['is_active'])

        self.stdout.write(
            self.style.SUCCESS(
                f'Created template version {cloned_template.version} (id={cloned_template.pk}) '
                f'from template {source_template.pk}; migrated '
                f'{migration_result.migrated_workflow_count if migration_result else 0} workflow(s).'
            )
        )
