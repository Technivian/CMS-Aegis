import random
from datetime import date, timedelta

from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from contracts.models import Contract, RiskLog, ComplianceChecklist

User = get_user_model()

class Command(BaseCommand):
    help = 'Seeds the database with mock data for the CLM platform.'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Starting database seeding...'))

        # Create a sample user
        user, created = User.objects.get_or_create(
            username='demouser',
            defaults={'first_name': 'Demo', 'last_name': 'User', 'email': 'demo@example.com'}
        )
        if created:
            user.set_password('demopassword')
            user.save()
            self.stdout.write(self.style.SUCCESS(f'Successfully created user: {user.username}'))

        # --- Seed Contracts ---
        contract_titles = [
            "Project Alpha MSA", "Project Beta NDA", "Vendor Services Agreement",
            "Software License for Gamma", "Q3 Marketing SOW", "Employee Agreement - J. Doe",
            "Partnership Deal with InnovateCorp", "Property Lease Agreement"
        ]
        for title in contract_titles:
            status = random.choice(Contract.ContractStatus.choices)[0]
            # Create some with upcoming/overdue milestones
            milestone = None
            if status not in [Contract.ContractStatus.DRAFT, Contract.ContractStatus.RENEWAL_TERMINATION]:
                if random.random() > 0.5:
                    milestone = date.today() + timedelta(days=random.randint(-15, 45))

            Contract.objects.get_or_create(
                title=title,
                created_by=user,
                defaults={
                    'counterparty': f'Counterparty {random.randint(1, 100)}',
                    'contract_type': random.choice(Contract.ContractType.choices)[0],
                    'jurisdiction': random.choice(Contract.Jurisdiction.choices)[0],
                    'value': random.uniform(5000, 500000),
                    'status': status,
                    'milestone_date': milestone,
                }
            )
        self.stdout.write(self.style.SUCCESS(f'Seeded {len(contract_titles)} contracts.'))

        # --- Seed Risk Logs ---
        risk_titles = ["Data Privacy Breach", "Scope Creep", "IP Infringement", "Termination Clause Ambiguity"]
        for title in risk_titles:
            RiskLog.objects.get_or_create(
                title=title,
                owner=user,
                defaults={
                    'description': f'Details about the risk: {title}.',
                    'risk_level': random.choice(RiskLog.RiskLevel.choices)[0],
                    'linked_contract': Contract.objects.order_by('?').first(),
                    'mitigation_steps': '1. Assess impact. 2. Notify stakeholders. 3. Implement control measures.',
                    'mitigation_status': random.choice(RiskLog.MitigationStatus.choices)[0],
                }
            )
        self.stdout.write(self.style.SUCCESS(f'Seeded {len(risk_titles)} risk logs.'))

        # --- Seed Compliance Checklists ---
        checklist_names = ["GDPR Compliance", "SOX Audit Checklist", "Internal Security Review"]
        for name in checklist_names:
            ComplianceChecklist.objects.get_or_create(
                name=name,
                defaults={
                    'regulation': name.split(' ')[0],
                    'reviewed_by': user,
                    'due_date': date.today() + timedelta(days=random.randint(10, 60)),
                    'status': random.choice(ComplianceChecklist.ComplianceStatus.choices)[0],
                }
            )
        self.stdout.write(self.style.SUCCESS(f'Seeded {len(checklist_names)} compliance checklists.'))

        self.stdout.write(self.style.SUCCESS('Database seeding complete!'))
