from django.core.management.base import BaseCommand

from contracts.models import WorkflowTemplate, WorkflowTemplateStep


class Command(BaseCommand):
    help = 'Create sample workflow templates.'

    def handle(self, *args, **options):
        templates_data = [
            {
                'name': 'Artist Licensing Agreement',
                'description': 'Standard workflow for artist licensing agreements',
                'category': WorkflowTemplate.Category.CONTRACT_REVIEW,
                'steps': ['Intake', 'Internal Review', 'External Review', 'Negotiation', 'Signature', 'Execution'],
            },
            {
                'name': 'Mutual NDA',
                'description': 'Standard workflow for mutual non-disclosure agreements',
                'category': WorkflowTemplate.Category.CONTRACT_REVIEW,
                'steps': ['Intake', 'Internal Review', 'External Review', 'Signature', 'Execution'],
            },
            {
                'name': 'Vendor Agreement',
                'description': 'Standard workflow for vendor procurement agreements',
                'category': WorkflowTemplate.Category.DUE_DILIGENCE,
                'steps': ['Intake', 'Risk Review', 'Negotiation', 'Signature', 'Execution'],
            },
            {
                'name': 'Compliance Review',
                'description': 'Standard workflow for regulatory and compliance review',
                'category': WorkflowTemplate.Category.COMPLIANCE,
                'steps': ['Intake', 'Compliance Review', 'Legal Sign-Off', 'Execution'],
            },
        ]

        for template_data in templates_data:
            template, created = WorkflowTemplate.objects.get_or_create(
                name=template_data['name'],
                version=1,
                defaults={
                    'description': template_data['description'],
                    'category': template_data['category'],
                    'is_active': True,
                },
            )

            if created:
                self.stdout.write(f"Created template: {template.name}")
                for order, step_name in enumerate(template_data['steps'], start=1):
                    WorkflowTemplateStep.objects.create(
                        template=template,
                        name=step_name,
                        order=order,
                    )
                    self.stdout.write(f"  Added step: {step_name} (order: {order})")
            else:
                self.stdout.write(f"Template already exists: {template.name} v{template.version}")

        self.stdout.write(self.style.SUCCESS('Successfully created workflow templates'))
