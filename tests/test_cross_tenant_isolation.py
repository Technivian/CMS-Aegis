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
