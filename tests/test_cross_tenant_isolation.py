"""
Cross-tenant isolation tests.

For every resource that carries an `organization` FK the suite verifies:
  - List views return ONLY the authenticated user's org records
  - Detail / Update views return 404 (not a live object) for another org's records

Models now fixed to filter via related-field org lookups (no direct FK):
  - Deadline  → filtered via contract__organization | matter__organization
  - RiskLog   → filtered via contract__organization | matter__organization
    - LegalTask → filtered via contract__organization | matter__organization
  - TrademarkRequest → filtered via client__organization | matter__organization

Direct organization FK models covered in this suite:
    - Budget
    - DueDiligenceProcess

Run:
  python manage.py test tests.test_cross_tenant_isolation
"""

import datetime
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model

from contracts.models import (
    Organization,
    OrganizationMembership,
    Client,
    Matter,
    Contract,
    Document,
    Deadline,
    LegalTask,
    RiskLog,
    TrademarkRequest,
    Budget,
    DueDiligenceProcess,
    Workflow,
    WorkflowStep,
    DataInventoryRecord,
    DSARRequest,
    Counterparty,
    ClauseCategory,
    ClauseTemplate,
    SignatureRequest,
    Subprocessor,
    TransferRecord,
    RetentionPolicy,
    LegalHold,
    ApprovalRule,
    ApprovalRequest,
    EthicalWall,
)

User = get_user_model()


# ---------------------------------------------------------------------------
# Base fixture mixin – creates two completely isolated orgs + users
# ---------------------------------------------------------------------------

class CrossTenantFixtureMixin:
    """
    Sets up:
      - org_a / user_a  (owner)
      - org_b / user_b  (owner)

    Both orgs come with their own Client → Matter → Contract chain so that
    related-field filtering tests get real FK linkage.
    """

    def setUp(self):
        # ---- Org A ----
        self.org_a = Organization.objects.create(name='Firm Alpha', slug='firm-alpha')
        self.user_a = User.objects.create_user(username='user_a', password='passA1234!')
        OrganizationMembership.objects.create(
            organization=self.org_a, user=self.user_a,
            role=OrganizationMembership.Role.OWNER, is_active=True,
        )

        # ---- Org B ----
        self.org_b = Organization.objects.create(name='Firm Beta', slug='firm-beta')
        self.user_b = User.objects.create_user(username='user_b', password='passB1234!')
        OrganizationMembership.objects.create(
            organization=self.org_b, user=self.user_b,
            role=OrganizationMembership.Role.OWNER, is_active=True,
        )

        # ---- Org A resources ----
        self.client_a = Client.objects.create(
            organization=self.org_a, name='Alpha Client',
        )
        self.matter_a = Matter.objects.create(
            organization=self.org_a, client=self.client_a,
            title='Alpha Matter', practice_area='CORPORATE',
            status='ACTIVE', open_date=datetime.date.today(),
        )
        self.contract_a = Contract.objects.create(
            organization=self.org_a, title='Alpha NDA',
            contract_type='NDA', status='ACTIVE',
            created_by=self.user_a,
        )
        self.document_a = Document.objects.create(
            organization=self.org_a, title='Alpha Doc',
            uploaded_by=self.user_a,
        )
        # Deadline linked to org_a via contract FK
        self.deadline_a = Deadline.objects.create(
            title='Alpha Deadline',
            due_date=datetime.date.today() + datetime.timedelta(days=30),
            contract=self.contract_a,
        )
        self.legal_task_a = LegalTask.objects.create(
            title='Alpha Task',
            description='Task A',
            due_date=datetime.date.today() + datetime.timedelta(days=10),
            contract=self.contract_a,
            assigned_to=self.user_a,
        )
        # RiskLog linked to org_a via contract FK
        self.risk_a = RiskLog.objects.create(
            title='Alpha Risk', description='A risk',
            contract=self.contract_a,
            created_by=self.user_a,
        )
        # TrademarkRequest linked to org_a via client FK
        self.trademark_a = TrademarkRequest.objects.create(
            mark_text='AlphaMark', description='desc',
            goods_services='software', filing_basis='use',
            client=self.client_a,
        )
        self.workflow_a = Workflow.objects.create(
            organization=self.org_a,
            title='Alpha Workflow',
            description='Workflow A',
            contract=self.contract_a,
            created_by=self.user_a,
        )
        self.workflow_step_a = WorkflowStep.objects.create(
            workflow=self.workflow_a,
            name='Alpha Step',
            order=1,
        )
        self.data_inventory_a = DataInventoryRecord.objects.create(
            organization=self.org_a,
            title='Alpha Data Map',
            data_categories='PII',
            data_subjects='Customers',
            purpose='Contract management',
            lawful_basis='CONTRACT',
            retention_period='7 years',
            client=self.client_a,
            created_by=self.user_a,
        )
        self.dsar_a = DSARRequest.objects.create(
            organization=self.org_a,
            request_type='ACCESS',
            status='RECEIVED',
            requester_name='Alice Alpha',
            requester_email='alice.alpha@example.com',
            description='Alpha request',
            received_date=datetime.date.today(),
            due_date=datetime.date.today() + datetime.timedelta(days=30),
            client=self.client_a,
            created_by=self.user_a,
        )
        self.counterparty_a = Counterparty.objects.create(
            organization=self.org_a,
            name='Alpha Counterparty',
        )
        self.clause_category_a = ClauseCategory.objects.create(
            organization=self.org_a,
            name='Alpha Category',
        )
        self.clause_a = ClauseTemplate.objects.create(
            organization=self.org_a,
            title='Alpha Clause',
            category=self.clause_category_a,
            content='Alpha clause content',
            created_by=self.user_a,
        )
        self.signature_a = SignatureRequest.objects.create(
            organization=self.org_a,
            contract=self.contract_a,
            signer_name='Alpha Signer',
            signer_email='alpha.signer@example.com',
            created_by=self.user_a,
        )
        self.subprocessor_a = Subprocessor.objects.create(
            organization=self.org_a,
            name='Alpha Processor',
            service_type='Hosting',
            country='Netherlands',
            created_by=self.user_a,
        )
        self.transfer_a = TransferRecord.objects.create(
            organization=self.org_a,
            title='Alpha Transfer',
            source_country='NL',
            destination_country='US',
            transfer_mechanism='SCC',
            data_categories='PII',
            subprocessor=self.subprocessor_a,
            contract=self.contract_a,
            created_by=self.user_a,
        )
        self.retention_a = RetentionPolicy.objects.create(
            organization=self.org_a,
            title='Alpha Retention',
            category='CONTRACTS',
            retention_period_days=365,
            created_by=self.user_a,
        )
        self.legal_hold_a = LegalHold.objects.create(
            organization=self.org_a,
            title='Alpha Hold',
            description='Hold A',
            matter=self.matter_a,
            client=self.client_a,
            hold_start_date=datetime.date.today(),
            issued_by=self.user_a,
        )
        self.approval_rule_a = ApprovalRule.objects.create(
            organization=self.org_a,
            name='Alpha Rule',
            trigger_type='VALUE_ABOVE',
            trigger_value='10000',
            approval_step='LEGAL',
            approver_role='ASSOCIATE',
            specific_approver=self.user_a,
        )
        self.approval_request_a = ApprovalRequest.objects.create(
            organization=self.org_a,
            contract=self.contract_a,
            rule=self.approval_rule_a,
            approval_step='LEGAL',
            assigned_to=self.user_a,
        )
        self.ethical_wall_a = EthicalWall.objects.create(
            organization=self.org_a,
            name='Alpha Wall',
            matter=self.matter_a,
            client=self.client_a,
            created_by=self.user_a,
        )

        # ---- Org B resources (parallel set so list queries have data to check) ----
        self.client_b = Client.objects.create(
            organization=self.org_b, name='Beta Client',
        )
        self.matter_b = Matter.objects.create(
            organization=self.org_b, client=self.client_b,
            title='Beta Matter', practice_area='LITIGATION',
            status='ACTIVE', open_date=datetime.date.today(),
        )
        self.contract_b = Contract.objects.create(
            organization=self.org_b, title='Beta NDA',
            contract_type='NDA', status='ACTIVE',
            created_by=self.user_b,
        )
        self.document_b = Document.objects.create(
            organization=self.org_b, title='Beta Doc',
            uploaded_by=self.user_b,
        )
        self.deadline_b = Deadline.objects.create(
            title='Beta Deadline',
            due_date=datetime.date.today() + datetime.timedelta(days=30),
            contract=self.contract_b,
        )
        self.legal_task_b = LegalTask.objects.create(
            title='Beta Task',
            description='Task B',
            due_date=datetime.date.today() + datetime.timedelta(days=10),
            contract=self.contract_b,
            assigned_to=self.user_b,
        )
        self.risk_b = RiskLog.objects.create(
            title='Beta Risk', description='A risk',
            contract=self.contract_b,
            created_by=self.user_b,
        )
        self.trademark_b = TrademarkRequest.objects.create(
            mark_text='BetaMark', description='desc',
            goods_services='software', filing_basis='use',
            client=self.client_b,
        )
        self.workflow_b = Workflow.objects.create(
            organization=self.org_b,
            title='Beta Workflow',
            description='Workflow B',
            contract=self.contract_b,
            created_by=self.user_b,
        )
        self.workflow_step_b = WorkflowStep.objects.create(
            workflow=self.workflow_b,
            name='Beta Step',
            order=1,
        )
        self.data_inventory_b = DataInventoryRecord.objects.create(
            organization=self.org_b,
            title='Beta Data Map',
            data_categories='PII',
            data_subjects='Customers',
            purpose='Contract management',
            lawful_basis='CONTRACT',
            retention_period='7 years',
            client=self.client_b,
            created_by=self.user_b,
        )
        self.dsar_b = DSARRequest.objects.create(
            organization=self.org_b,
            request_type='ACCESS',
            status='RECEIVED',
            requester_name='Bob Beta',
            requester_email='bob.beta@example.com',
            description='Beta request',
            received_date=datetime.date.today(),
            due_date=datetime.date.today() + datetime.timedelta(days=30),
            client=self.client_b,
            created_by=self.user_b,
        )
        self.counterparty_b = Counterparty.objects.create(
            organization=self.org_b,
            name='Beta Counterparty',
        )
        self.clause_category_b = ClauseCategory.objects.create(
            organization=self.org_b,
            name='Beta Category',
        )
        self.clause_b = ClauseTemplate.objects.create(
            organization=self.org_b,
            title='Beta Clause',
            category=self.clause_category_b,
            content='Beta clause content',
            created_by=self.user_b,
        )
        self.signature_b = SignatureRequest.objects.create(
            organization=self.org_b,
            contract=self.contract_b,
            signer_name='Beta Signer',
            signer_email='beta.signer@example.com',
            created_by=self.user_b,
        )
        self.subprocessor_b = Subprocessor.objects.create(
            organization=self.org_b,
            name='Beta Processor',
            service_type='Hosting',
            country='Germany',
            created_by=self.user_b,
        )
        self.transfer_b = TransferRecord.objects.create(
            organization=self.org_b,
            title='Beta Transfer',
            source_country='DE',
            destination_country='US',
            transfer_mechanism='SCC',
            data_categories='PII',
            subprocessor=self.subprocessor_b,
            contract=self.contract_b,
            created_by=self.user_b,
        )
        self.retention_b = RetentionPolicy.objects.create(
            organization=self.org_b,
            title='Beta Retention',
            category='CONTRACTS',
            retention_period_days=365,
            created_by=self.user_b,
        )
        self.legal_hold_b = LegalHold.objects.create(
            organization=self.org_b,
            title='Beta Hold',
            description='Hold B',
            matter=self.matter_b,
            client=self.client_b,
            hold_start_date=datetime.date.today(),
            issued_by=self.user_b,
        )
        self.approval_rule_b = ApprovalRule.objects.create(
            organization=self.org_b,
            name='Beta Rule',
            trigger_type='VALUE_ABOVE',
            trigger_value='10000',
            approval_step='LEGAL',
            approver_role='ASSOCIATE',
            specific_approver=self.user_b,
        )
        self.approval_request_b = ApprovalRequest.objects.create(
            organization=self.org_b,
            contract=self.contract_b,
            rule=self.approval_rule_b,
            approval_step='LEGAL',
            assigned_to=self.user_b,
        )
        self.ethical_wall_b = EthicalWall.objects.create(
            organization=self.org_b,
            name='Beta Wall',
            matter=self.matter_b,
            client=self.client_b,
            created_by=self.user_b,
        )


class NullOrganizationAuditCommandTest(TestCase):
    def test_audit_passes_when_no_null_org_rows_exist(self):
        stdout = StringIO()

        call_command('audit_null_organizations', stdout=stdout)

        self.assertIn('No NULL organization rows found.', stdout.getvalue())

    def test_audit_fails_when_tenant_owned_row_has_null_org(self):
        Workflow.objects.create(title='Orphan Workflow')
        stdout = StringIO()

        with self.assertRaises(CommandError):
            call_command('audit_null_organizations', stdout=stdout)

        self.assertIn('Workflow: 1 row(s)', stdout.getvalue())


# ===========================================================================
# 1. Direct org-FK models: Contract, Document, Client, Matter
# ===========================================================================

class ContractIsolationTest(CrossTenantFixtureMixin, TestCase):
    """Contracts carry organization FK – isolation is enforced by scope_queryset."""

    def test_list_shows_only_own_org(self):
        self.client.login(username='user_b', password='passB1234!')
        response = self.client.get(reverse('contracts:contract_list'))
        self.assertEqual(response.status_code, 200)
        ids = [c['id'] if isinstance(c, dict) else c.id
               for c in response.context.get('contracts', [])]
        self.assertNotIn(self.contract_a.id, ids,
                         'contract_a (Org A) must not appear in Org B list')
        self.assertIn(self.contract_b.id, ids,
                      'contract_b (Org B) must appear in Org B list')

    def test_detail_cross_org_returns_404(self):
        self.client.login(username='user_b', password='passB1234!')
        url = reverse('contracts:contract_detail', kwargs={'pk': self.contract_a.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404,
                         'Accessing another org contract detail must return 404')

    def test_update_cross_org_returns_404(self):
        self.client.login(username='user_b', password='passB1234!')
        url = reverse('contracts:contract_update', kwargs={'pk': self.contract_a.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404,
                         'Accessing another org contract update must return 404')


class DocumentIsolationTest(CrossTenantFixtureMixin, TestCase):
    """Documents carry organization FK."""

    def test_list_shows_only_own_org(self):
        self.client.login(username='user_b', password='passB1234!')
        response = self.client.get(reverse('contracts:document_list'))
        self.assertEqual(response.status_code, 200)
        ids = [d.id for d in response.context.get('documents', [])]
        self.assertNotIn(self.document_a.id, ids)
        self.assertIn(self.document_b.id, ids)

    def test_detail_cross_org_returns_404(self):
        self.client.login(username='user_b', password='passB1234!')
        url = reverse('contracts:document_detail', kwargs={'pk': self.document_a.pk})
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_update_cross_org_returns_404(self):
        self.client.login(username='user_b', password='passB1234!')
        url = reverse('contracts:document_update', kwargs={'pk': self.document_a.pk})
        self.assertEqual(self.client.get(url).status_code, 404)


class ClientIsolationTest(CrossTenantFixtureMixin, TestCase):
    """Clients carry organization FK."""

    def test_list_shows_only_own_org(self):
        self.client.login(username='user_b', password='passB1234!')
        response = self.client.get(reverse('contracts:client_list'))
        self.assertEqual(response.status_code, 200)
        ids = [c.id for c in response.context.get('clients', [])]
        self.assertNotIn(self.client_a.id, ids)
        self.assertIn(self.client_b.id, ids)

    def test_detail_cross_org_returns_404(self):
        self.client.login(username='user_b', password='passB1234!')
        url = reverse('contracts:client_detail', kwargs={'pk': self.client_a.pk})
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_update_cross_org_returns_404(self):
        self.client.login(username='user_b', password='passB1234!')
        url = reverse('contracts:client_update', kwargs={'pk': self.client_a.pk})
        self.assertEqual(self.client.get(url).status_code, 404)


class MatterIsolationTest(CrossTenantFixtureMixin, TestCase):
    """Matters carry organization FK."""

    def test_list_shows_only_own_org(self):
        self.client.login(username='user_b', password='passB1234!')
        response = self.client.get(reverse('contracts:matter_list'))
        self.assertEqual(response.status_code, 200)
        ids = [m.id for m in response.context.get('matters', [])]
        self.assertNotIn(self.matter_a.id, ids)
        self.assertIn(self.matter_b.id, ids)

    def test_detail_cross_org_returns_404(self):
        self.client.login(username='user_b', password='passB1234!')
        url = reverse('contracts:matter_detail', kwargs={'pk': self.matter_a.pk})
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_update_cross_org_returns_404(self):
        self.client.login(username='user_b', password='passB1234!')
        url = reverse('contracts:matter_update', kwargs={'pk': self.matter_a.pk})
        self.assertEqual(self.client.get(url).status_code, 404)


# ===========================================================================
# 2. Related-field isolated models (no direct org FK – filtered via FK chain)
# ===========================================================================

class DeadlineIsolationTest(CrossTenantFixtureMixin, TestCase):
    """
    Deadline has no direct organization FK. Isolation is enforced in
    DeadlineListView / DeadlineUpdateView via contract__organization | matter__organization.
    """

    def test_list_excludes_other_org(self):
        self.client.login(username='user_b', password='passB1234!')
        response = self.client.get(reverse('contracts:deadline_list') + '?show=all')
        self.assertEqual(response.status_code, 200)
        ids = [d.id for d in response.context.get('deadlines', [])]
        self.assertNotIn(self.deadline_a.id, ids,
                         'deadline_a (via contract_a of Org A) must not appear for Org B')
        self.assertIn(self.deadline_b.id, ids)

    def test_update_cross_org_returns_404(self):
        self.client.login(username='user_b', password='passB1234!')
        url = reverse('contracts:deadline_update', kwargs={'pk': self.deadline_a.pk})
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_complete_cross_org_returns_404(self):
        self.client.login(username='user_b', password='passB1234!')
        url = reverse('contracts:deadline_complete', kwargs={'pk': self.deadline_a.pk})
        self.assertEqual(self.client.post(url).status_code, 404)


class LegalTaskIsolationTest(CrossTenantFixtureMixin, TestCase):
    """
    LegalTask has no direct organization FK. Isolation enforced via
    contract__organization | matter__organization.
    """

    def test_list_excludes_other_org(self):
        self.client.login(username='user_b', password='passB1234!')
        response = self.client.get(reverse('contracts:legal_task_kanban'))
        self.assertEqual(response.status_code, 200)
        ids = [t.id for t in response.context.get('legal_tasks', [])]
        self.assertNotIn(self.legal_task_a.id, ids)
        self.assertIn(self.legal_task_b.id, ids)

    def test_update_cross_org_returns_404(self):
        self.client.login(username='user_b', password='passB1234!')
        url = reverse('contracts:legal_task_update', kwargs={'pk': self.legal_task_a.pk})
        self.assertEqual(self.client.get(url).status_code, 404)


class RiskLogIsolationTest(CrossTenantFixtureMixin, TestCase):
    """
    RiskLog has no direct organization FK. Isolation enforced via
    contract__organization | matter__organization.
    """

    def test_list_excludes_other_org(self):
        self.client.login(username='user_b', password='passB1234!')
        response = self.client.get(reverse('contracts:risk_log_list'))
        self.assertEqual(response.status_code, 200)
        ids = [r.id for r in response.context.get('risk_logs', [])]
        self.assertNotIn(self.risk_a.id, ids,
                         'risk_a (via contract_a of Org A) must not appear for Org B')
        self.assertIn(self.risk_b.id, ids)

    def test_update_cross_org_returns_404(self):
        self.client.login(username='user_b', password='passB1234!')
        url = reverse('contracts:risk_log_update', kwargs={'pk': self.risk_a.pk})
        self.assertEqual(self.client.get(url).status_code, 404)


class TrademarkRequestIsolationTest(CrossTenantFixtureMixin, TestCase):
    """
    TrademarkRequest has no direct organization FK. Isolation enforced via
    client__organization | matter__organization.
    """

    def test_list_excludes_other_org(self):
        self.client.login(username='user_b', password='passB1234!')
        response = self.client.get(reverse('contracts:trademark_request_list'))
        self.assertEqual(response.status_code, 200)
        ids = [t.id for t in response.context.get('trademark_requests', [])]
        self.assertNotIn(self.trademark_a.id, ids,
                         'trademark_a (via client_a of Org A) must not appear for Org B')
        self.assertIn(self.trademark_b.id, ids)

    def test_detail_cross_org_returns_404(self):
        self.client.login(username='user_b', password='passB1234!')
        url = reverse('contracts:trademark_request_detail', kwargs={'pk': self.trademark_a.pk})
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_update_cross_org_returns_404(self):
        self.client.login(username='user_b', password='passB1234!')
        url = reverse('contracts:trademark_request_update', kwargs={'pk': self.trademark_a.pk})
        self.assertEqual(self.client.get(url).status_code, 404)


# ===========================================================================
# 3. Unauthenticated access must redirect to login (never expose data)
# ===========================================================================

class UnauthenticatedAccessTest(TestCase):
    """All resource endpoints must redirect anonymous users to the login page."""

    URLS = [
        ('contracts:contract_list', {}),
        ('contracts:document_list', {}),
        ('contracts:client_list', {}),
        ('contracts:matter_list', {}),
        ('contracts:legal_task_kanban', {}),
        ('contracts:risk_log_list', {}),
        ('contracts:deadline_list', {}),
        ('contracts:trademark_request_list', {}),
        ('contracts:budget_list', {}),
        ('contracts:due_diligence_list', {}),
        ('dashboard', {}),
    ]

    def test_all_list_endpoints_redirect_anonymous(self):
        for name, kwargs in self.URLS:
            with self.subTest(url_name=name):
                response = self.client.get(reverse(name, kwargs=kwargs))
                self.assertIn(
                    response.status_code, [302, 301],
                    f'{name} should redirect unauthenticated users',
                )
                self.assertIn(
                    '/login/', response['Location'],
                    f'{name} must redirect to login page',
                )


# ===========================================================================
# 4. Previously-known gaps — now fixed via migration 0005
# ===========================================================================

class BudgetIsolationTest(CrossTenantFixtureMixin, TestCase):
    """Budget cross-tenant isolation – enforced via organization FK (migration 0005)."""

    def setUp(self):
        super().setUp()
        self.budget_a = Budget.objects.create(
            organization=self.org_a,
            year=2025, quarter='Q1',
            department='AlphaDept',
            allocated_amount='50000.00',
            created_by=self.user_a,
        )
        self.budget_b = Budget.objects.create(
            organization=self.org_b,
            year=2025, quarter='Q1',
            department='BetaDept',
            allocated_amount='50000.00',
            created_by=self.user_b,
        )

    def test_list_excludes_other_org(self):
        self.client.login(username='user_b', password='passB1234!')
        response = self.client.get(reverse('contracts:budget_list'))
        self.assertEqual(response.status_code, 200)
        ids = [b.id for b in response.context.get('budgets', [])]
        self.assertNotIn(self.budget_a.id, ids)
        self.assertIn(self.budget_b.id, ids)

    def test_detail_cross_org_returns_404(self):
        self.client.login(username='user_b', password='passB1234!')
        url = reverse('contracts:budget_detail', kwargs={'pk': self.budget_a.pk})
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_update_cross_org_returns_404(self):
        self.client.login(username='user_b', password='passB1234!')
        url = reverse('contracts:budget_update', kwargs={'pk': self.budget_a.pk})
        self.assertEqual(self.client.get(url).status_code, 404)


class WorkflowIsolationTest(CrossTenantFixtureMixin, TestCase):
    def test_workflow_dashboard_excludes_other_org(self):
        self.client.login(username='user_b', password='passB1234!')
        response = self.client.get(reverse('contracts:workflow_dashboard'))
        self.assertEqual(response.status_code, 200)
        ids = [w.id for w in response.context.get('workflows', [])]
        self.assertNotIn(self.workflow_a.id, ids)
        self.assertIn(self.workflow_b.id, ids)

    def test_workflow_detail_cross_org_returns_404(self):
        self.client.login(username='user_b', password='passB1234!')
        url = reverse('contracts:workflow_detail', kwargs={'pk': self.workflow_a.pk})
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_workflow_step_update_cross_org_returns_404(self):
        self.client.login(username='user_b', password='passB1234!')
        url = reverse('contracts:update_workflow_step', kwargs={'pk': self.workflow_step_a.pk})
        self.assertEqual(self.client.post(url, {'status': 'COMPLETED'}).status_code, 404)


class PrivacyAndSearchIsolationTest(CrossTenantFixtureMixin, TestCase):
    def test_privacy_dashboard_is_scoped(self):
        self.client.login(username='user_b', password='passB1234!')
        response = self.client.get(reverse('contracts:privacy_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['data_inventory_count'], 1)
        self.assertEqual(response.context['dsar_pending'], 1)
        recent_dsars = list(response.context['recent_dsars'])
        ids = [dsar.id for dsar in recent_dsars]
        self.assertNotIn(self.dsar_a.id, ids)
        self.assertIn(self.dsar_b.id, ids)

    def test_global_search_excludes_other_org_results(self):
        self.client.login(username='user_b', password='passB1234!')
        response = self.client.get(reverse('contracts:global_search'), {'q': 'Alpha'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context['results']['contracts']), [])
        self.assertEqual(list(response.context['results']['clients']), [])


class CounterpartyIsolationTest(CrossTenantFixtureMixin, TestCase):
    def test_list_excludes_other_org(self):
        self.client.login(username='user_b', password='passB1234!')
        response = self.client.get(reverse('contracts:counterparty_list'))
        self.assertEqual(response.status_code, 200)
        ids = [c.id for c in response.context.get('counterparties', [])]
        self.assertNotIn(self.counterparty_a.id, ids)
        self.assertIn(self.counterparty_b.id, ids)

    def test_detail_cross_org_returns_404(self):
        self.client.login(username='user_b', password='passB1234!')
        url = reverse('contracts:counterparty_detail', kwargs={'pk': self.counterparty_a.pk})
        self.assertEqual(self.client.get(url).status_code, 404)


class ClauseIsolationTest(CrossTenantFixtureMixin, TestCase):
    def test_list_excludes_other_org(self):
        self.client.login(username='user_b', password='passB1234!')
        response = self.client.get(reverse('contracts:clause_template_list'))
        self.assertEqual(response.status_code, 200)
        ids = [c.id for c in response.context.get('clauses', [])]
        category_ids = [c.id for c in response.context.get('categories', [])]
        self.assertNotIn(self.clause_a.id, ids)
        self.assertIn(self.clause_b.id, ids)
        self.assertNotIn(self.clause_category_a.id, category_ids)
        self.assertIn(self.clause_category_b.id, category_ids)

    def test_detail_cross_org_returns_404(self):
        self.client.login(username='user_b', password='passB1234!')
        url = reverse('contracts:clause_template_detail', kwargs={'pk': self.clause_a.pk})
        self.assertEqual(self.client.get(url).status_code, 404)


class SignatureIsolationTest(CrossTenantFixtureMixin, TestCase):
    def test_list_excludes_other_org(self):
        self.client.login(username='user_b', password='passB1234!')
        response = self.client.get(reverse('contracts:signature_request_list'))
        self.assertEqual(response.status_code, 200)
        ids = [s.id for s in response.context.get('signatures', [])]
        self.assertNotIn(self.signature_a.id, ids)
        self.assertIn(self.signature_b.id, ids)

    def test_detail_cross_org_returns_404(self):
        self.client.login(username='user_b', password='passB1234!')
        url = reverse('contracts:signature_request_detail', kwargs={'pk': self.signature_a.pk})
        self.assertEqual(self.client.get(url).status_code, 404)


class PrivacySupportIsolationTest(CrossTenantFixtureMixin, TestCase):
    def test_data_inventory_list_excludes_other_org(self):
        self.client.login(username='user_b', password='passB1234!')
        response = self.client.get(reverse('contracts:data_inventory_list'))
        self.assertEqual(response.status_code, 200)
        ids = [r.id for r in response.context.get('records', [])]
        self.assertNotIn(self.data_inventory_a.id, ids)
        self.assertIn(self.data_inventory_b.id, ids)

    def test_dsar_list_excludes_other_org(self):
        self.client.login(username='user_b', password='passB1234!')
        response = self.client.get(reverse('contracts:dsar_list'))
        self.assertEqual(response.status_code, 200)
        ids = [r.id for r in response.context.get('requests', [])]
        self.assertNotIn(self.dsar_a.id, ids)
        self.assertIn(self.dsar_b.id, ids)

    def test_subprocessor_list_excludes_other_org(self):
        self.client.login(username='user_b', password='passB1234!')
        response = self.client.get(reverse('contracts:subprocessor_list'))
        self.assertEqual(response.status_code, 200)
        ids = [r.id for r in response.context.get('subprocessors', [])]
        self.assertNotIn(self.subprocessor_a.id, ids)
        self.assertIn(self.subprocessor_b.id, ids)

    def test_transfer_list_excludes_other_org(self):
        self.client.login(username='user_b', password='passB1234!')
        response = self.client.get(reverse('contracts:transfer_record_list'))
        self.assertEqual(response.status_code, 200)
        ids = [r.id for r in response.context.get('transfers', [])]
        self.assertNotIn(self.transfer_a.id, ids)
        self.assertIn(self.transfer_b.id, ids)

    def test_retention_list_excludes_other_org(self):
        self.client.login(username='user_b', password='passB1234!')
        response = self.client.get(reverse('contracts:retention_policy_list'))
        self.assertEqual(response.status_code, 200)
        ids = [r.id for r in response.context.get('policies', [])]
        self.assertNotIn(self.retention_a.id, ids)
        self.assertIn(self.retention_b.id, ids)

    def test_legal_hold_detail_cross_org_returns_404(self):
        self.client.login(username='user_b', password='passB1234!')
        url = reverse('contracts:legal_hold_detail', kwargs={'pk': self.legal_hold_a.pk})
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_approval_rule_list_excludes_other_org(self):
        self.client.login(username='user_b', password='passB1234!')
        response = self.client.get(reverse('contracts:approval_rule_list'))
        self.assertEqual(response.status_code, 200)
        ids = [r.id for r in response.context.get('rules', [])]
        self.assertNotIn(self.approval_rule_a.id, ids)
        self.assertIn(self.approval_rule_b.id, ids)

    def test_approval_request_list_excludes_other_org(self):
        self.client.login(username='user_b', password='passB1234!')
        response = self.client.get(reverse('contracts:approval_request_list'))
        self.assertEqual(response.status_code, 200)
        ids = [r.id for r in response.context.get('approvals', [])]
        self.assertNotIn(self.approval_request_a.id, ids)
        self.assertIn(self.approval_request_b.id, ids)

    def test_ethical_wall_list_excludes_other_org(self):
        self.client.login(username='user_b', password='passB1234!')
        response = self.client.get(reverse('contracts:ethical_wall_list'))
        self.assertEqual(response.status_code, 200)
        ids = [r.id for r in response.context.get('walls', [])]
        self.assertNotIn(self.ethical_wall_a.id, ids)
        self.assertIn(self.ethical_wall_b.id, ids)


class ScopedFormIsolationTest(CrossTenantFixtureMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.client.login(username='user_b', password='passB1234!')
        self.today = datetime.date.today().isoformat()
        self.future = (datetime.date.today() + datetime.timedelta(days=30)).isoformat()

    def assert_invalid_create(self, url_name, data, model):
        before = model.objects.count()
        response = self.client.post(reverse(url_name), data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(model.objects.count(), before)
        self.assertTrue(response.context['form'].errors)

    def assert_invalid_update(self, url_name, obj, data, field_name, expected_value):
        response = self.client.post(reverse(url_name, kwargs={'pk': obj.pk}), data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['form'].errors)
        obj.refresh_from_db()
        self.assertEqual(getattr(obj, field_name), expected_value)

    def test_create_forms_reject_cross_org_foreign_keys(self):
        cases = [
            (
                'contracts:workflow_create',
                {'title': 'Bad Workflow', 'description': 'x', 'contract': self.contract_a.pk},
                Workflow,
            ),
            (
                'contracts:clause_template_create',
                {'title': 'Bad Clause', 'category': self.clause_category_a.pk, 'content': 'bad'},
                ClauseTemplate,
            ),
            (
                'contracts:ethical_wall_create',
                {
                    'name': 'Bad Wall',
                    'description': 'x',
                    'matter': self.matter_a.pk,
                    'client': self.client_a.pk,
                    'restricted_users': [self.user_a.pk],
                    'is_active': 'on',
                    'reason': 'bad',
                },
                EthicalWall,
            ),
            (
                'contracts:signature_request_create',
                {
                    'contract': self.contract_a.pk,
                    'document': self.document_a.pk,
                    'signer_name': 'Bad Signer',
                    'signer_email': 'bad@example.com',
                    'status': 'PENDING',
                    'order': 0,
                },
                SignatureRequest,
            ),
            (
                'contracts:data_inventory_create',
                {
                    'title': 'Bad Record',
                    'data_categories': 'PII',
                    'data_subjects': 'Customers',
                    'purpose': 'Testing',
                    'lawful_basis': 'CONTRACT',
                    'retention_period': '1 year',
                    'client': self.client_a.pk,
                },
                DataInventoryRecord,
            ),
            (
                'contracts:dsar_create',
                {
                    'request_type': 'ACCESS',
                    'status': 'RECEIVED',
                    'requester_name': 'Bad Requester',
                    'requester_email': 'bad-requester@example.com',
                    'description': 'bad',
                    'received_date': self.today,
                    'due_date': self.future,
                    'client': self.client_a.pk,
                    'assigned_to': self.user_a.pk,
                },
                DSARRequest,
            ),
            (
                'contracts:transfer_record_create',
                {
                    'title': 'Bad Transfer',
                    'source_country': 'NL',
                    'destination_country': 'US',
                    'transfer_mechanism': 'SCC',
                    'data_categories': 'PII',
                    'subprocessor': self.subprocessor_a.pk,
                    'contract': self.contract_a.pk,
                },
                TransferRecord,
            ),
            (
                'contracts:legal_hold_create',
                {
                    'title': 'Bad Hold',
                    'description': 'bad',
                    'status': 'ACTIVE',
                    'matter': self.matter_a.pk,
                    'client': self.client_a.pk,
                    'custodians': [self.user_a.pk],
                    'hold_start_date': self.today,
                },
                LegalHold,
            ),
            (
                'contracts:approval_rule_create',
                {
                    'name': 'Bad Rule',
                    'description': 'bad',
                    'trigger_type': 'VALUE_ABOVE',
                    'trigger_value': '100',
                    'approval_step': 'LEGAL',
                    'approver_role': 'ASSOCIATE',
                    'specific_approver': self.user_a.pk,
                    'sla_hours': 48,
                    'escalation_after_hours': 72,
                    'order': 0,
                },
                ApprovalRule,
            ),
            (
                'contracts:approval_request_create',
                {
                    'contract': self.contract_a.pk,
                    'approval_step': 'LEGAL',
                    'status': 'PENDING',
                    'assigned_to': self.user_a.pk,
                    'comments': 'bad',
                },
                ApprovalRequest,
            ),
        ]

        for url_name, data, model in cases:
            with self.subTest(url_name=url_name):
                self.assert_invalid_create(url_name, data, model)

    def test_update_forms_reject_cross_org_foreign_keys(self):
        cases = [
            (
                'contracts:clause_template_update',
                self.clause_b,
                {'title': self.clause_b.title, 'category': self.clause_category_a.pk, 'content': self.clause_b.content},
                'category_id',
                self.clause_category_b.id,
            ),
            (
                'contracts:ethical_wall_update',
                self.ethical_wall_b,
                {
                    'name': self.ethical_wall_b.name,
                    'description': self.ethical_wall_b.description,
                    'matter': self.matter_a.pk,
                    'client': self.client_a.pk,
                    'restricted_users': [self.user_a.pk],
                    'is_active': 'on',
                    'reason': self.ethical_wall_b.reason,
                },
                'matter_id',
                self.matter_b.id,
            ),
            (
                'contracts:signature_request_update',
                self.signature_b,
                {
                    'contract': self.contract_a.pk,
                    'document': self.document_a.pk,
                    'signer_name': self.signature_b.signer_name,
                    'signer_email': self.signature_b.signer_email,
                    'status': self.signature_b.status,
                    'order': self.signature_b.order,
                },
                'contract_id',
                self.contract_b.id,
            ),
            (
                'contracts:data_inventory_update',
                self.data_inventory_b,
                {
                    'title': self.data_inventory_b.title,
                    'data_categories': self.data_inventory_b.data_categories,
                    'data_subjects': self.data_inventory_b.data_subjects,
                    'purpose': self.data_inventory_b.purpose,
                    'lawful_basis': self.data_inventory_b.lawful_basis,
                    'retention_period': self.data_inventory_b.retention_period,
                    'client': self.client_a.pk,
                },
                'client_id',
                self.client_b.id,
            ),
            (
                'contracts:dsar_update',
                self.dsar_b,
                {
                    'request_type': self.dsar_b.request_type,
                    'status': self.dsar_b.status,
                    'requester_name': self.dsar_b.requester_name,
                    'requester_email': self.dsar_b.requester_email,
                    'description': self.dsar_b.description,
                    'received_date': self.today,
                    'due_date': self.future,
                    'client': self.client_a.pk,
                    'assigned_to': self.user_a.pk,
                },
                'client_id',
                self.client_b.id,
            ),
            (
                'contracts:transfer_record_update',
                self.transfer_b,
                {
                    'title': self.transfer_b.title,
                    'source_country': self.transfer_b.source_country,
                    'destination_country': self.transfer_b.destination_country,
                    'transfer_mechanism': self.transfer_b.transfer_mechanism,
                    'data_categories': self.transfer_b.data_categories,
                    'subprocessor': self.subprocessor_a.pk,
                    'contract': self.contract_a.pk,
                },
                'contract_id',
                self.contract_b.id,
            ),
            (
                'contracts:legal_hold_update',
                self.legal_hold_b,
                {
                    'title': self.legal_hold_b.title,
                    'description': self.legal_hold_b.description,
                    'status': self.legal_hold_b.status,
                    'matter': self.matter_a.pk,
                    'client': self.client_a.pk,
                    'custodians': [self.user_a.pk],
                    'hold_start_date': self.today,
                },
                'matter_id',
                self.matter_b.id,
            ),
            (
                'contracts:approval_rule_update',
                self.approval_rule_b,
                {
                    'name': self.approval_rule_b.name,
                    'description': self.approval_rule_b.description,
                    'trigger_type': self.approval_rule_b.trigger_type,
                    'trigger_value': self.approval_rule_b.trigger_value,
                    'approval_step': self.approval_rule_b.approval_step,
                    'approver_role': self.approval_rule_b.approver_role,
                    'specific_approver': self.user_a.pk,
                    'sla_hours': self.approval_rule_b.sla_hours,
                    'escalation_after_hours': self.approval_rule_b.escalation_after_hours,
                    'order': self.approval_rule_b.order,
                },
                'specific_approver_id',
                self.user_b.id,
            ),
            (
                'contracts:approval_request_update',
                self.approval_request_b,
                {
                    'contract': self.contract_a.pk,
                    'approval_step': self.approval_request_b.approval_step,
                    'status': self.approval_request_b.status,
                    'assigned_to': self.user_a.pk,
                    'comments': self.approval_request_b.comments,
                },
                'contract_id',
                self.contract_b.id,
            ),
        ]

        for url_name, obj, data, field_name, expected_value in cases:
            with self.subTest(url_name=url_name):
                self.assert_invalid_update(url_name, obj, data, field_name, expected_value)


class DueDiligenceActionIsolationTest(CrossTenantFixtureMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.dd_a = DueDiligenceProcess.objects.create(
            organization=self.org_a,
            title='Alpha DD',
            transaction_type='ACQUISITION',
            target_company='Target A',
            start_date=datetime.date.today(),
            target_completion_date=datetime.date.today() + datetime.timedelta(days=90),
            lead_attorney=self.user_a,
        )
        self.dd_task_a = self.dd_a.dd_tasks.create(
            title='Alpha DD Task',
            category='LEGAL',
            due_date=datetime.date.today() + datetime.timedelta(days=10),
        )

    def test_toggle_dd_item_cross_org_returns_404(self):
        self.client.login(username='user_b', password='passB1234!')
        url = reverse('contracts:toggle_dd_item', kwargs={'pk': self.dd_task_a.pk})
        self.assertEqual(self.client.post(url).status_code, 404)


class DueDiligenceIsolationTest(CrossTenantFixtureMixin, TestCase):
    """DueDiligenceProcess cross-tenant isolation – enforced via organization FK (migration 0005)."""

    def setUp(self):
        super().setUp()
        self.dd_a = DueDiligenceProcess.objects.create(
            organization=self.org_a,
            title='Alpha DD', transaction_type='ACQUISITION',
            target_company='Target A',
            start_date=datetime.date.today(),
            target_completion_date=datetime.date.today() + datetime.timedelta(days=90),
            lead_attorney=self.user_a,
        )
        self.dd_b = DueDiligenceProcess.objects.create(
            organization=self.org_b,
            title='Beta DD', transaction_type='MERGER',
            target_company='Target B',
            start_date=datetime.date.today(),
            target_completion_date=datetime.date.today() + datetime.timedelta(days=90),
            lead_attorney=self.user_b,
        )

    def test_list_excludes_other_org(self):
        self.client.login(username='user_b', password='passB1234!')
        response = self.client.get(reverse('contracts:due_diligence_list'))
        self.assertEqual(response.status_code, 200)
        ids = [p.id for p in response.context.get('processes', [])]
        self.assertNotIn(self.dd_a.id, ids)
        self.assertIn(self.dd_b.id, ids)

    def test_detail_cross_org_returns_404(self):
        self.client.login(username='user_b', password='passB1234!')
        url = reverse('contracts:due_diligence_detail', kwargs={'pk': self.dd_a.pk})
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_update_cross_org_returns_404(self):
        self.client.login(username='user_b', password='passB1234!')
        url = reverse('contracts:due_diligence_update', kwargs={'pk': self.dd_a.pk})
        self.assertEqual(self.client.get(url).status_code, 404)
