from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from contracts.models import (
    Client, Matter, Contract, Document, TimeEntry, Invoice, TrustAccount,
    TrustTransaction, Deadline, LegalTask, RiskLog, UserProfile, ConflictCheck,
    Organization, OrganizationMembership,
)
from contracts.services.starter_content import ensure_org_starter_content
from datetime import date, timedelta
from decimal import Decimal

User = get_user_model()


class Command(BaseCommand):
    help = 'Seeds the database with sample data for development'

    def handle(self, *args, **options):
        if User.objects.filter(username='admin').exists():
            self.stdout.write(self.style.WARNING('Seed data already exists. Skipping.'))
            return

        admin = User.objects.create_superuser('admin', 'admin@boltonclm.com', 'admin123', first_name='Admin', last_name='User')
        UserProfile.objects.get_or_create(user=admin, defaults={'role': 'ADMIN'})

        attorney1 = User.objects.create_user('jsmith', 'jsmith@boltonclm.com', 'password123', first_name='John', last_name='Smith')
        UserProfile.objects.get_or_create(user=attorney1, defaults={'role': 'PARTNER', 'bar_number': 'BAR-001', 'hourly_rate': Decimal('450')})

        attorney2 = User.objects.create_user('sjones', 'sjones@boltonclm.com', 'password123', first_name='Sarah', last_name='Jones')
        UserProfile.objects.get_or_create(user=attorney2, defaults={'role': 'SENIOR_ASSOCIATE', 'bar_number': 'BAR-002', 'hourly_rate': Decimal('350')})

        paralegal = User.objects.create_user('mwilson', 'mwilson@boltonclm.com', 'password123', first_name='Mike', last_name='Wilson')
        UserProfile.objects.get_or_create(user=paralegal, defaults={'role': 'PARALEGAL', 'hourly_rate': Decimal('150')})

        organization = Organization.objects.create(name='Demo Firm', slug='demo-firm')
        for user, role in [
            (admin, OrganizationMembership.Role.OWNER),
            (attorney1, OrganizationMembership.Role.ADMIN),
            (attorney2, OrganizationMembership.Role.ADMIN),
            (paralegal, OrganizationMembership.Role.MEMBER),
        ]:
            OrganizationMembership.objects.create(
                organization=organization,
                user=user,
                role=role,
                is_active=True,
            )
        ensure_org_starter_content(organization)

        client1 = Client.objects.create(
            organization=organization,
            name='Acme Corporation', client_type='CORPORATE', status='ACTIVE',
            email='legal@acme.com', phone='555-0100', industry='Technology',
            address='123 Tech Blvd', city='San Francisco', state='CA', zip_code='94105',
            primary_contact='Jane Doe', primary_contact_email='jane@acme.com',
            responsible_attorney=attorney1, originating_attorney=attorney1,
            created_by=admin
        )
        client2 = Client.objects.create(
            organization=organization,
            name='Global Industries LLC', client_type='CORPORATE', status='ACTIVE',
            email='legal@globalind.com', phone='555-0200', industry='Manufacturing',
            address='456 Industrial Way', city='Chicago', state='IL', zip_code='60601',
            primary_contact='Bob Smith', primary_contact_email='bob@globalind.com',
            responsible_attorney=attorney2, originating_attorney=attorney1,
            created_by=admin
        )
        client3 = Client.objects.create(
            organization=organization,
            name='Sarah Williams', client_type='INDIVIDUAL', status='ACTIVE',
            email='swilliams@email.com', phone='555-0300',
            responsible_attorney=attorney2, created_by=admin
        )

        today = date.today()

        matter1 = Matter.objects.create(
            organization=organization,
            title='Merger Agreement - Acme/TechStart', client=client1,
            practice_area='CORPORATE', status='ACTIVE',
            responsible_attorney=attorney1, originating_attorney=attorney1,
            billing_type='HOURLY', budget_amount=Decimal('50000'),
            open_date=today - timedelta(days=30), created_by=admin
        )
        matter2 = Matter.objects.create(
            organization=organization,
            title='Employment Dispute - Williams', client=client3,
            practice_area='LABOR', status='ACTIVE',
            responsible_attorney=attorney2,
            billing_type='HOURLY', budget_amount=Decimal('15000'),
            open_date=today - timedelta(days=60),
            opposing_party='Former Employer Inc', opposing_counsel='Law Firm LLP',
            court_name='Superior Court of California', case_number='2026-CV-12345',
            statute_of_limitations=today + timedelta(days=180), created_by=admin
        )
        matter3 = Matter.objects.create(
            organization=organization,
            title='IP Licensing - Global Industries', client=client2,
            practice_area='IP', status='ACTIVE',
            responsible_attorney=attorney1, originating_attorney=attorney2,
            billing_type='FLAT_FEE', budget_amount=Decimal('25000'),
            open_date=today - timedelta(days=15), created_by=admin
        )

        contract1 = Contract.objects.create(
            organization=organization,
            title='Master Services Agreement - Acme', contract_type='MSA',
            content='This Master Services Agreement...', status='ACTIVE',
            counterparty='TechStart Inc', value=Decimal('500000'),
            start_date=today - timedelta(days=90), end_date=today + timedelta(days=275),
            client=client1, matter=matter1, created_by=attorney1
        )
        contract2 = Contract.objects.create(
            organization=organization,
            title='NDA - Global Industries', contract_type='NDA',
            content='This Non-Disclosure Agreement...', status='ACTIVE',
            counterparty='Global Industries LLC', value=Decimal('0'),
            start_date=today - timedelta(days=60), end_date=today + timedelta(days=305),
            client=client2, matter=matter3, created_by=attorney2
        )
        contract3 = Contract.objects.create(
            organization=organization,
            title='Employment Settlement Draft', contract_type='SETTLEMENT',
            content='Settlement terms...', status='DRAFT',
            counterparty='Former Employer Inc', value=Decimal('75000'),
            client=client3, matter=matter2, created_by=attorney2
        )

        for i in range(5):
            TimeEntry.objects.create(
                organization=organization,
                matter=matter1, user=attorney1,
                date=today - timedelta(days=i * 3),
                hours=Decimal(str(round(1.5 + i * 0.5, 2))),
                description=f'Review merger documents - session {i+1}',
                activity_type='REVIEW', rate=Decimal('450'), is_billable=True
            )
        for i in range(3):
            TimeEntry.objects.create(
                organization=organization,
                matter=matter2, user=attorney2,
                date=today - timedelta(days=i * 2),
                hours=Decimal(str(round(2.0 + i * 0.25, 2))),
                description=f'Prepare court filings - session {i+1}',
                activity_type='COURT_APPEARANCE', rate=Decimal('350'), is_billable=True
            )

        Invoice.objects.create(
            organization=organization,
            client=client1, matter=matter1,
            issue_date=today - timedelta(days=15), due_date=today + timedelta(days=15),
            subtotal=Decimal('5625'), tax_rate=Decimal('0'),
            status='SENT', payment_terms='Net 30', created_by=admin
        )
        Invoice.objects.create(
            organization=organization,
            client=client3, matter=matter2,
            issue_date=today - timedelta(days=45), due_date=today - timedelta(days=15),
            subtotal=Decimal('2100'), tax_rate=Decimal('0'),
            status='OVERDUE', payment_terms='Net 30', created_by=admin
        )

        trust1 = TrustAccount.objects.create(
            client=client1, matter=matter1, account_name='Acme IOLTA',
            balance=Decimal('25000'), created_by=admin
        )
        TrustTransaction.objects.create(
            account=trust1, transaction_type='DEPOSIT', amount=Decimal('25000'),
            description='Initial retainer deposit', created_by=admin
        )

        Deadline.objects.create(
            title='File Motion to Dismiss', deadline_type='COURT_FILING',
            priority='HIGH', due_date=today + timedelta(days=5),
            matter=matter2, assigned_to=attorney2, created_by=admin
        )
        Deadline.objects.create(
            title='Merger Due Diligence Complete', deadline_type='REGULATORY',
            priority='CRITICAL', due_date=today + timedelta(days=14),
            matter=matter1, assigned_to=attorney1, created_by=admin
        )
        Deadline.objects.create(
            title='NDA Annual Review', deadline_type='CONTRACT_RENEWAL',
            priority='MEDIUM', due_date=today + timedelta(days=30),
            contract=contract2, assigned_to=attorney2, created_by=admin
        )

        LegalTask.objects.create(
            title='Draft interrogatories', description='Prepare initial set of interrogatories',
            priority='HIGH', status='PENDING',
            due_date=today + timedelta(days=7), assigned_to=attorney2,
            matter=matter2
        )
        LegalTask.objects.create(
            title='Review IP portfolio', description='Complete review of patent portfolio',
            priority='MEDIUM', status='IN_PROGRESS',
            due_date=today + timedelta(days=10), assigned_to=attorney1,
            matter=matter3
        )

        RiskLog.objects.create(
            title='Antitrust Concern - Merger', description='Potential antitrust issues with market concentration',
            risk_level='HIGH', mitigation_plan='Engage antitrust specialist for review',
            contract=contract1, matter=matter1, created_by=admin
        )

        ConflictCheck.objects.create(
            client=client1, matter=matter1, checked_party='TechStart Inc',
            checked_party_type='Corporation', status='CLEAR',
            checked_by=attorney1
        )
        ConflictCheck.objects.create(
            client=client3, matter=matter2, checked_party='Former Employer Inc',
            checked_party_type='Corporation', status='CLEAR',
            checked_by=attorney2
        )

        self.stdout.write(self.style.SUCCESS('Seed data created successfully!'))
        self.stdout.write(f'  Admin user: admin / admin123')
        self.stdout.write(f'  Demo organization: {organization.name}')
        self.stdout.write(f'  3 clients, 3 matters, 3 contracts')
        self.stdout.write(f'  8 time entries, 2 invoices, 1 trust account')
        self.stdout.write(f'  3 deadlines, 2 tasks, 1 risk, 2 conflict checks')
