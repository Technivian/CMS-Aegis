
import random
from datetime import date, timedelta

from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from contracts.models import (
    Contract, RiskLog, ComplianceChecklist, ChecklistItem, Tag, Note, 
    WorkflowStep, ContractVersion, NegotiationThread, TrademarkRequest, 
    LegalTask, WorkflowTemplate, WorkflowTemplateStep, Workflow
)

User = get_user_model()

class Command(BaseCommand):
    help = 'Seeds the database with comprehensive mock data for the CLM platform.'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Starting comprehensive database seeding...'))

        # Create multiple users for testing
        users = []
        for i, (username, first_name, last_name) in enumerate([
            ('demouser', 'Demo', 'User'),
            ('alice', 'Alice', 'Johnson'),
            ('bob', 'Bob', 'Smith'),
            ('carol', 'Carol', 'Davis'),
            ('david', 'David', 'Wilson')
        ]):
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    'first_name': first_name, 
                    'last_name': last_name, 
                    'email': f'{username}@example.com'
                }
            )
            if created:
                user.set_password('demopassword')
                user.save()
                self.stdout.write(f'Created user: {user.username}')
            users.append(user)

        main_user = users[0]

        # Create tags
        tag_names = [
            'High Priority', 'Urgent', 'Revenue Critical', 'Legal Review Required',
            'IP Sensitive', 'International', 'Renewable', 'Master Agreement',
            'Amendment', 'Termination', 'SOX Compliance', 'GDPR', 'Confidential'
        ]
        tags = []
        for tag_name in tag_names:
            tag, created = Tag.objects.get_or_create(name=tag_name)
            tags.append(tag)
        self.stdout.write(f'Created {len(tags)} tags.')

        # Create comprehensive contracts with all statuses and types
        contract_data = [
            ("Global Master Service Agreement - TechCorp", "TechCorp Inc.", "MSA", "US", 2500000, "EXECUTION"),
            ("Artist Licensing Deal - Spotify", "Spotify Technology S.A.", "OTHER", "EU", 850000, "NEGOTIATION"),
            ("Mutual NDA - Apple Inc.", "Apple Inc.", "NDA", "US", None, "SIGNATURE"),
            ("Employment Agreement - Sarah Connor", "Individual", "EMPLOYMENT", "US", 120000, "EXECUTION"),
            ("SLA for Cloud Services - AWS", "Amazon Web Services", "SLA", "US", 450000, "INTERNAL_REVIEW"),
            ("Artist License - Universal Music", "Universal Music Group", "OTHER", "UK", 1200000, "EXTERNAL_REVIEW"),
            ("Vendor SOW - Marketing Agency", "Creative Solutions Ltd", "SOW", "UK", 75000, "DRAFT"),
            ("IP License Agreement - Bolton Labs", "Bolton Adhesives Research", "OTHER", "US", 3500000, "NEGOTIATION"),
            ("Data Processing Agreement - GDPR", "DataSecure EU", "OTHER", "EU", 180000, "SIGNATURE"),
            ("Partnership Agreement - Asia Pacific", "APAC Ventures", "MSA", "APAC", 5200000, "EXECUTION"),
            ("Software License - Adobe Creative", "Adobe Systems", "OTHER", "US", 95000, "RENEWAL_TERMINATION"),
            ("Trademark License - Brand Portfolio", "Brand Holdings LLC", "OTHER", "US", 680000, "INTERNAL_REVIEW"),
        ]

        contracts = []
        for i, (title, counterparty, contract_type, jurisdiction, value, status) in enumerate(contract_data):
            # Create milestone dates
            if status in ['EXECUTION', 'RENEWAL_TERMINATION']:
                milestone = date.today() + timedelta(days=random.randint(-30, 180))
            elif status in ['SIGNATURE', 'NEGOTIATION']:
                milestone = date.today() + timedelta(days=random.randint(5, 45))
            else:
                milestone = None

            contract = Contract.objects.create(
                title=title,
                counterparty=counterparty,
                contract_type=contract_type,
                jurisdiction=jurisdiction,
                value=value,
                status=status,
                milestone_date=milestone,
                created_by=random.choice(users)
            )
            
            # Add tags to contracts
            contract.tags.set(random.sample(tags, random.randint(1, 4)))
            contracts.append(contract)

        self.stdout.write(f'Created {len(contracts)} contracts with all statuses and types.')

        # Create notes for contracts
        note_texts = [
            "Client requested changes to payment terms in section 4.2",
            "Legal team approved all liability clauses",
            "Waiting for executive signature - urgent priority",
            "Compliance review completed successfully",
            "Negotiation call scheduled for next Tuesday",
            "IP terms need clarification from technical team",
            "Financial review pending - value exceeds approval threshold",
            "Contract ready for final execution"
        ]
        
        for contract in contracts[:8]:  # Add notes to first 8 contracts
            for _ in range(random.randint(1, 3)):
                Note.objects.create(
                    contract=contract,
                    text=random.choice(note_texts),
                    created_by=random.choice(users)
                )

        # Create contract versions
        for contract in contracts[:6]:  # Add versions to first 6 contracts
            for version in range(1, random.randint(2, 5)):
                ContractVersion.objects.create(
                    contract=contract,
                    version_number=version,
                    content_snapshot=f"Contract content for {contract.title} version {version}",
                    approved_by=random.choice(users) if version > 1 else None
                )

        # Create negotiation threads
        for contract in contracts[:5]:  # Add negotiation threads to first 5 contracts
            for round_num in range(1, random.randint(2, 4)):
                NegotiationThread.objects.create(
                    contract=contract,
                    round_number=round_num,
                    internal_note=f"Internal discussion round {round_num} for {contract.title}",
                    external_note=f"External communication round {round_num}",
                    author=random.choice(users)
                )

        # Create comprehensive trademark requests
        trademark_data = [
            ("United States", "35", "REGISTERED"),
            ("European Union", "09", "IN_REVIEW"), 
            ("United Kingdom", "42", "FILED"),
            ("Japan", "35", "PENDING"),
            ("Canada", "09", "REGISTERED"),
            ("Australia", "42", "REJECTED"),
            ("Germany", "35", "IN_REVIEW"),
            ("France", "09", "FILED"),
        ]

        for region, class_num, status in trademark_data:
            renewal_date = None
            if status == "REGISTERED":
                renewal_date = date.today() + timedelta(days=random.randint(365, 2555))  # 1-7 years
            
            TrademarkRequest.objects.create(
                region=region,
                class_number=class_num,
                status=status,
                renewal_deadline=renewal_date,
                owner=random.choice(users)
            )

        self.stdout.write(f'Created {len(trademark_data)} trademark requests.')

        # Create comprehensive legal tasks
        task_data = [
            ("Review Bolton Adhesive Master Agreement", "Contract Review", "HIGH", "TODO"),
            ("File trademark renewal - EU Region", "IP Management", "MEDIUM", "IN_PROGRESS"),
            ("Update privacy policy for GDPR compliance", "Compliance", "HIGH", "TODO"),
            ("Negotiate licensing terms with Universal", "Contract Negotiation", "HIGH", "IN_PROGRESS"),
            ("Annual SOX compliance audit", "Compliance", "MEDIUM", "DONE"),
            ("Review employment contracts - Q4 batch", "HR Legal", "LOW", "TODO"),
            ("Update vendor agreements template", "Template Management", "MEDIUM", "IN_PROGRESS"),
            ("IP infringement investigation", "IP Protection", "HIGH", "TODO"),
            ("Board resolution documentation", "Corporate", "MEDIUM", "DONE"),
            ("Export control compliance review", "International Trade", "HIGH", "TODO"),
            ("Software license audit", "IT Compliance", "MEDIUM", "IN_PROGRESS"),
            ("Partnership agreement amendments", "Business Development", "LOW", "TODO"),
        ]

        for title, task_type, priority, status in task_data:
            due_date = None
            if status != "DONE":
                due_date = date.today() + timedelta(days=random.randint(1, 90))
            
            LegalTask.objects.create(
                title=title,
                task_type=task_type,
                priority=priority,
                status=status,
                subject=f"Detailed description for {title}",
                is_recurring=random.choice([True, False]),
                assigned_to=random.choice(users),
                due_date=due_date
            )

        self.stdout.write(f'Created {len(task_data)} legal tasks.')

        # Create comprehensive risk logs
        risk_data = [
            ("IP Infringement Risk - Music Licensing", "HIGH", "IN_PROGRESS"),
            ("GDPR Non-Compliance Exposure", "MEDIUM", "MITIGATED"),
            ("Contract Termination Clause Ambiguity", "HIGH", "PENDING"),
            ("Export Control Violation Risk", "MEDIUM", "IN_PROGRESS"),
            ("Data Breach Liability", "HIGH", "MITIGATED"),
            ("Vendor Concentration Risk", "LOW", "PENDING"),
            ("Currency Exchange Rate Exposure", "MEDIUM", "IN_PROGRESS"),
            ("Regulatory Change Impact", "MEDIUM", "PENDING"),
            ("Key Personnel Dependency", "LOW", "MITIGATED"),
            ("Technology Obsolescence Risk", "MEDIUM", "IN_PROGRESS"),
        ]

        for title, risk_level, mitigation_status in risk_data:
            RiskLog.objects.create(
                title=title,
                description=f"Detailed risk assessment for {title}. This risk requires careful monitoring and mitigation planning.",
                risk_level=risk_level,
                linked_contract=random.choice(contracts) if random.choice([True, False]) else None,
                owner=random.choice(users),
                mitigation_steps=f"1. Assess impact of {title}\n2. Implement control measures\n3. Monitor ongoing status\n4. Report to stakeholders",
                mitigation_status=mitigation_status
            )

        self.stdout.write(f'Created {len(risk_data)} risk logs.')

        # Create comprehensive compliance checklists
        checklist_data = [
            ("GDPR Data Protection Compliance", "GDPR", "IN_PROGRESS"),
            ("SOX Financial Controls Audit", "Sarbanes-Oxley", "NOT_STARTED"),
            ("ISO 27001 Security Review", "ISO 27001", "COMPLETE"),
            ("CCPA Privacy Rights Assessment", "CCPA", "IN_PROGRESS"),
            ("Export Administration Regulations", "EAR", "NOT_STARTED"),
            ("Anti-Corruption Due Diligence", "FCPA", "COMPLETE"),
            ("Environmental Compliance Review", "EPA", "IN_PROGRESS"),
            ("Employment Law Compliance", "Employment", "NOT_STARTED"),
            ("Intellectual Property Audit", "IP", "COMPLETE"),
            ("Contract Management Standards", "Internal", "IN_PROGRESS"),
        ]

        checklists = []
        for name, regulation, status in checklist_data:
            due_date = None
            if status != "COMPLETE":
                due_date = date.today() + timedelta(days=random.randint(14, 120))
            
            checklist = ComplianceChecklist.objects.create(
                name=name,
                regulation=regulation,
                status=status,
                reviewed_by=random.choice(users),
                due_date=due_date
            )
            checklists.append(checklist)

        # Create checklist items
        checklist_items = [
            "Review data processing agreements",
            "Update privacy notices",
            "Conduct data mapping exercise",
            "Implement access controls",
            "Document security procedures",
            "Train staff on compliance requirements",
            "Establish incident response procedures",
            "Review vendor contracts",
            "Conduct risk assessments",
            "Implement monitoring systems",
        ]

        for checklist in checklists:
            num_items = random.randint(5, 8)
            selected_items = random.sample(checklist_items, num_items)
            for item_text in selected_items:
                ChecklistItem.objects.create(
                    checklist=checklist,
                    text=f"{item_text} for {checklist.regulation}",
                    is_checked=random.choice([True, False])
                )

        self.stdout.write(f'Created {len(checklist_data)} compliance checklists with items.')

        # Create workflow templates if they don't exist
        template_data = [
            {
                'name': 'Standard Contract Review',
                'description': 'Standard workflow for contract review and approval',
                'contract_type': 'OTHER',
                'steps': [
                    ('INTERNAL_REVIEW', 1),
                    ('EXTERNAL_REVIEW', 2),
                    ('SIGNATURE', 3),
                    ('EXECUTION', 4),
                ]
            },
            {
                'name': 'High-Value Agreement Process',
                'description': 'Enhanced workflow for high-value agreements',
                'contract_type': 'MSA',
                'steps': [
                    ('INTERNAL_REVIEW', 1),
                    ('EXTERNAL_REVIEW', 2),
                    ('NEGOTIATION', 3),
                    ('SIGNATURE', 4),
                    ('EXECUTION', 5),
                ]
            },
            {
                'name': 'Employment Contract Workflow',
                'description': 'Specialized workflow for employment agreements',
                'contract_type': 'EMPLOYMENT',
                'steps': [
                    ('INTERNAL_REVIEW', 1),
                    ('SIGNATURE', 2),
                    ('EXECUTION', 3),
                ]
            },
        ]

        templates = []
        for template_info in template_data:
            template, created = WorkflowTemplate.objects.get_or_create(
                name=template_info['name'],
                defaults={
                    'description': template_info['description'],
                    'contract_type': template_info['contract_type'],
                    'created_by': main_user,
                    'is_active': True,
                }
            )
            
            if created:
                for step_type, order in template_info['steps']:
                    WorkflowTemplateStep.objects.create(
                        template=template,
                        step_type=step_type,
                        order=order,
                        estimated_days=random.randint(2, 7),
                        is_required=True
                    )
            templates.append(template)

        # Create workflows for some contracts
        workflow_contracts = contracts[:6]  # First 6 contracts get workflows
        for i, contract in enumerate(workflow_contracts):
            template = templates[i % len(templates)]
            
            workflow = Workflow.objects.create(
                name=f"Workflow for {contract.title}",
                contract=contract,
                template=template,
                status='ACTIVE' if i < 4 else 'COMPLETED',
                created_by=main_user,
                projected_completion=date.today() + timedelta(days=random.randint(30, 90))
            )

            # Create workflow steps from template
            for template_step in template.template_steps.all():
                step_status = 'COMPLETED' if workflow.status == 'COMPLETED' or template_step.order <= 2 else 'PENDING'
                if template_step.order == 3 and workflow.status == 'ACTIVE':
                    step_status = 'IN_PROGRESS'

                step = WorkflowStep.objects.create(
                    workflow=workflow,
                    contract=contract,
                    step_type=template_step.step_type,
                    order=template_step.order,
                    status=step_status,
                    assigned_to=random.choice(users),
                    due_date=date.today() + timedelta(days=template_step.order * 7),
                    notes=f"Step {template_step.order} notes for {contract.title}" if step_status != 'PENDING' else ""
                )

                # Set current step for active workflows
                if workflow.status == 'ACTIVE' and step_status == 'IN_PROGRESS':
                    workflow.current_step = step
                    workflow.save()

        self.stdout.write(f'Created workflows for {len(workflow_contracts)} contracts.')

        # Summary
        self.stdout.write(self.style.SUCCESS('=== SEEDING COMPLETE ==='))
        self.stdout.write(f'Users: {User.objects.count()}')
        self.stdout.write(f'Tags: {Tag.objects.count()}')
        self.stdout.write(f'Contracts: {Contract.objects.count()}')
        self.stdout.write(f'Notes: {Note.objects.count()}')
        self.stdout.write(f'Contract Versions: {ContractVersion.objects.count()}')
        self.stdout.write(f'Negotiation Threads: {NegotiationThread.objects.count()}')
        self.stdout.write(f'Trademark Requests: {TrademarkRequest.objects.count()}')
        self.stdout.write(f'Legal Tasks: {LegalTask.objects.count()}')
        self.stdout.write(f'Risk Logs: {RiskLog.objects.count()}')
        self.stdout.write(f'Compliance Checklists: {ComplianceChecklist.objects.count()}')
        self.stdout.write(f'Checklist Items: {ChecklistItem.objects.count()}')
        self.stdout.write(f'Workflow Templates: {WorkflowTemplate.objects.count()}')
        self.stdout.write(f'Workflows: {Workflow.objects.count()}')
        self.stdout.write(f'Workflow Steps: {WorkflowStep.objects.count()}')
        self.stdout.write(self.style.SUCCESS('All dropdowns and functions now have comprehensive test data!'))
