"""
Cross-tenant isolation tests.

For every resource that carries an `organization` FK the suite verifies:
  - List views return ONLY the authenticated user's org records
  - Detail / Update views return 404 (not a live object) for another org's records

Models now fixed to filter via related-field org lookups (no direct FK):
    - Deadline  → filtered via related case/configuration ownership
    - CareSignal → filtered via related case/configuration ownership
    - CareTask → filtered via related case/configuration ownership
    - PlacementRequest → filtered via related provider/configuration ownership

Direct organization FK models covered in this suite:
    - Budget
    - CaseIntakeProcess

Run:
  python manage.py test tests.test_cross_tenant_isolation
"""

import datetime

from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model

from contracts.models import (
    CareCase,
    Organization,
    OrganizationMembership,
    Client,
    CareConfiguration,
    Document,
    Deadline,
    CareTask,
    CareSignal,
    PlacementRequest,
    Budget,
    CaseIntakeProcess,
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

    Both orgs come with their own Client → Configuration → CareCase chain so that
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
        self.matter_a = CareConfiguration.objects.create(
            organization=self.org_a, client=self.client_a,
            title='Alpha Configuration',
            status='ACTIVE', open_date=datetime.date.today(),
        )
        self.contract_a = CareCase.objects.create(
            organization=self.org_a, title='Alpha NDA',
            contract_type='NDA', status='ACTIVE',
            created_by=self.user_a,
        )
        self.document_a = Document.objects.create(
            organization=self.org_a, title='Alpha Doc',
            uploaded_by=self.user_a,
        )
        # Deadline linked to org_a via case FK
        self.deadline_a = Deadline.objects.create(
            title='Alpha Deadline',
            due_date=datetime.date.today() + datetime.timedelta(days=30),
            case_record=self.contract_a,
        )
        self.legal_task_a = CareTask.objects.create(
            title='Alpha Task',
            description='Task A',
            due_date=datetime.date.today() + datetime.timedelta(days=10),
            case_record=self.contract_a,
            assigned_to=self.user_a,
        )
        # CareSignal linked to org_a via case FK
        self.risk_a = CareSignal.objects.create(
            title='Alpha Risk', description='A risk',
            case_record=self.contract_a,
            created_by=self.user_a,
        )
        # PlacementRequest linked to org_a via client FK
        self.placement_a = PlacementRequest.objects.create(
            mark_text='AlphaMark', description='desc',
            goods_services='software', filing_basis='use',
            client=self.client_a,
        )

        # ---- Org B resources (parallel set so list queries have data to check) ----
        self.client_b = Client.objects.create(
            organization=self.org_b, name='Beta Client',
        )
        self.matter_b = CareConfiguration.objects.create(
            organization=self.org_b, client=self.client_b,
            title='Beta Configuration',
            status='ACTIVE', open_date=datetime.date.today(),
        )
        self.contract_b = CareCase.objects.create(
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
            case_record=self.contract_b,
        )
        self.legal_task_b = CareTask.objects.create(
            title='Beta Task',
            description='Task B',
            due_date=datetime.date.today() + datetime.timedelta(days=10),
            case_record=self.contract_b,
            assigned_to=self.user_b,
        )
        self.risk_b = CareSignal.objects.create(
            title='Beta Risk', description='A risk',
            case_record=self.contract_b,
            created_by=self.user_b,
        )
        self.placement_b = PlacementRequest.objects.create(
            mark_text='BetaMark', description='desc',
            goods_services='software', filing_basis='use',
            client=self.client_b,
        )


# ===========================================================================
# 1. Direct org-FK models: CareCase, Document, Client, CareConfiguration
# ===========================================================================

class CareCaseIsolationTest(CrossTenantFixtureMixin, TestCase):
    """CareCase records carry organization FK and must stay tenant-scoped."""

    def test_list_shows_only_own_org(self):
        self.client.login(username='user_b', password='passB1234!')
        response = self.client.get(reverse('careon:case_list'))
        self.assertEqual(response.status_code, 200)
        body = response.content.decode('utf-8')
        self.assertIn('Zorgintakes', body)
        self.assertNotIn('Alpha NDA', body)

    def test_detail_cross_org_returns_404(self):
        self.client.login(username='user_b', password='passB1234!')
        url = reverse('careon:case_detail', kwargs={'pk': self.contract_a.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404,
                         'Accessing another org case detail must return 404')

    def test_update_cross_org_returns_404(self):
        self.client.login(username='user_b', password='passB1234!')
        url = reverse('careon:configuration_update', kwargs={'pk': self.matter_a.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404,
                         'Accessing another org configuration update must return 404')


class DocumentIsolationTest(CrossTenantFixtureMixin, TestCase):
    """Documents carry organization FK."""

    def test_list_shows_only_own_org(self):
        self.client.login(username='user_b', password='passB1234!')
        response = self.client.get(reverse('careon:document_list'))
        self.assertEqual(response.status_code, 200)
        ids = [d.id for d in response.context.get('documents', [])]
        self.assertNotIn(self.document_a.id, ids)
        self.assertIn(self.document_b.id, ids)

    def test_detail_cross_org_returns_404(self):
        self.client.login(username='user_b', password='passB1234!')
        url = reverse('careon:document_detail', kwargs={'pk': self.document_a.pk})
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_update_cross_org_returns_404(self):
        self.client.login(username='user_b', password='passB1234!')
        url = reverse('careon:document_update', kwargs={'pk': self.document_a.pk})
        self.assertEqual(self.client.get(url).status_code, 404)


class ClientIsolationTest(CrossTenantFixtureMixin, TestCase):
    """Clients carry organization FK."""

    def test_list_shows_only_own_org(self):
        self.client.login(username='user_b', password='passB1234!')
        response = self.client.get(reverse('careon:client_list'))
        self.assertEqual(response.status_code, 200)
        ids = [c.id for c in response.context.get('clients', [])]
        self.assertNotIn(self.client_a.id, ids)
        self.assertIn(self.client_b.id, ids)

    def test_detail_cross_org_returns_404(self):
        self.client.login(username='user_b', password='passB1234!')
        url = reverse('careon:client_detail', kwargs={'pk': self.client_a.pk})
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_update_cross_org_returns_404(self):
        self.client.login(username='user_b', password='passB1234!')
        url = reverse('careon:client_update', kwargs={'pk': self.client_a.pk})
        self.assertEqual(self.client.get(url).status_code, 404)


class CareConfigurationIsolationTest(CrossTenantFixtureMixin, TestCase):
    """CareConfiguration records carry organization FK."""

    def test_list_redirects_to_municipality_workspace(self):
        self.client.login(username='user_b', password='passB1234!')
        response = self.client.get(reverse('careon:configuration_list'))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('careon:municipality_list'), response['Location'])

    def test_detail_cross_org_returns_404(self):
        self.client.login(username='user_b', password='passB1234!')
        url = reverse('careon:configuration_detail', kwargs={'pk': self.matter_a.pk})
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_update_cross_org_returns_404(self):
        self.client.login(username='user_b', password='passB1234!')
        url = reverse('careon:configuration_update', kwargs={'pk': self.matter_a.pk})
        self.assertEqual(self.client.get(url).status_code, 404)


class GlobalSearchIsolationTest(CrossTenantFixtureMixin, TestCase):
    """Global search must only return organization-scoped records for the active user."""

    def setUp(self):
        super().setUp()
        self.contract_a.title = 'Shared Search Alpha Case'
        self.contract_a.save(update_fields=['title'])
        self.contract_b.title = 'Shared Search Beta Case'
        self.contract_b.save(update_fields=['title'])

        self.client_a.name = 'Shared Search Alpha Provider'
        self.client_a.save(update_fields=['name'])
        self.client_b.name = 'Shared Search Beta Provider'
        self.client_b.save(update_fields=['name'])

        self.matter_a.title = 'Shared Search Alpha Region'
        self.matter_a.save(update_fields=['title'])
        self.matter_b.title = 'Shared Search Beta Region'
        self.matter_b.save(update_fields=['title'])

        self.document_a.title = 'Shared Search Alpha Document'
        self.document_a.save(update_fields=['title'])
        self.document_b.title = 'Shared Search Beta Document'
        self.document_b.save(update_fields=['title'])

    def test_global_search_excludes_other_org_records(self):
        self.client.login(username='user_b', password='passB1234!')

        response = self.client.get(reverse('careon:global_search'), {'q': 'Shared Search'})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Shared Search Beta Case')
        self.assertContains(response, 'Shared Search Beta Provider')
        self.assertContains(response, 'Shared Search Beta Region')
        self.assertContains(response, 'Shared Search Beta Document')
        self.assertNotContains(response, 'Shared Search Alpha Case')
        self.assertNotContains(response, 'Shared Search Alpha Provider')
        self.assertNotContains(response, 'Shared Search Alpha Region')
        self.assertNotContains(response, 'Shared Search Alpha Document')


# ===========================================================================
# 2. Related-field isolated models (no direct org FK – filtered via FK chain)
# ===========================================================================

class DeadlineIsolationTest(CrossTenantFixtureMixin, TestCase):
    """
    Deadline has no direct organization FK. Isolation is enforced in
    DeadlineListView / DeadlineUpdateView via related case/configuration ownership.
    """

    def test_list_excludes_other_org(self):
        self.client.login(username='user_b', password='passB1234!')
        response = self.client.get(reverse('careon:deadline_list') + '?show=all')
        self.assertEqual(response.status_code, 200)
        ids = [d.id for d in response.context.get('deadlines', [])]
        self.assertNotIn(self.deadline_a.id, ids,
                         'deadline_a (via case_a of Org A) must not appear for Org B')
        self.assertIn(self.deadline_b.id, ids)

    def test_update_cross_org_returns_404(self):
        self.client.login(username='user_b', password='passB1234!')
        url = reverse('careon:deadline_update', kwargs={'pk': self.deadline_a.pk})
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_complete_cross_org_returns_404(self):
        self.client.login(username='user_b', password='passB1234!')
        url = reverse('careon:deadline_complete', kwargs={'pk': self.deadline_a.pk})
        self.assertEqual(self.client.post(url).status_code, 404)


class CareTaskIsolationTest(CrossTenantFixtureMixin, TestCase):
    """
    CareTask has no direct organization FK. Isolation enforced via
    related case/configuration ownership.
    """

    def test_list_excludes_other_org(self):
        self.client.login(username='user_b', password='passB1234!')
        response = self.client.get(reverse('careon:care_task_kanban'))
        self.assertEqual(response.status_code, 200)
        ids = [t.id for t in response.context.get('care_tasks', [])]
        self.assertNotIn(self.legal_task_a.id, ids)
        self.assertIn(self.legal_task_b.id, ids)

    def test_update_cross_org_returns_404(self):
        self.client.login(username='user_b', password='passB1234!')
        url = reverse('careon:task_update', kwargs={'pk': self.legal_task_a.pk})
        self.assertEqual(self.client.get(url).status_code, 404)


class CareSignalIsolationTest(CrossTenantFixtureMixin, TestCase):
    """
    CareSignal has no direct organization FK. Isolation enforced via
    related case/configuration ownership.
    """

    def test_list_excludes_other_org(self):
        self.client.login(username='user_b', password='passB1234!')
        response = self.client.get(reverse('careon:signal_list'))
        self.assertEqual(response.status_code, 200)
        ids = [m.id for m in response.context.get('signals', [])]
        self.assertNotIn(self.risk_a.id, ids,
                 'risk_a (Org A) must not appear for Org B')

    def test_update_cross_org_returns_404(self):
        self.client.login(username='user_b', password='passB1234!')
        url = reverse('careon:signal_update', kwargs={'pk': self.risk_a.pk})
        self.assertEqual(self.client.get(url).status_code, 404)


class PlacementRequestIsolationTest(CrossTenantFixtureMixin, TestCase):
    """
    PlacementRequest has no direct organization FK. Isolation enforced via
    related provider/configuration ownership.
    """

    def test_list_excludes_other_org(self):
        self.client.login(username='user_b', password='passB1234!')
        response = self.client.get(reverse('careon:placement_list'))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8')
        self.assertNotIn('AlphaMark', content,
                 'Org A placements must not appear for Org B user')

    def test_detail_cross_org_returns_404(self):
        self.client.login(username='user_b', password='passB1234!')
        url = reverse('careon:placement_detail', kwargs={'pk': self.placement_a.pk})
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_update_cross_org_returns_404(self):
        self.client.login(username='user_b', password='passB1234!')
        url = reverse('careon:placement_update', kwargs={'pk': self.placement_a.pk})
        self.assertEqual(self.client.get(url).status_code, 404)


# ===========================================================================
# 3. Unauthenticated access must redirect to login (never expose data)
# ===========================================================================

class UnauthenticatedAccessTest(TestCase):
    """All resource endpoints must redirect anonymous users to the login page."""

    URLS = [
        ('careon:case_list', {}),
        ('careon:document_list', {}),
        ('careon:client_list', {}),
        ('careon:configuration_list', {}),
        ('careon:task_list', {}),
        ('careon:signal_list', {}),
        ('careon:deadline_list', {}),
        ('careon:placement_list', {}),
        ('careon:budget_list', {}),
        ('careon:intake_list', {}),
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
        response = self.client.get(reverse('careon:budget_list'))
        self.assertEqual(response.status_code, 200)
        ids = [b.id for b in response.context.get('budgets', [])]
        self.assertNotIn(self.budget_a.id, ids)
        self.assertIn(self.budget_b.id, ids)

    def test_detail_cross_org_returns_404(self):
        self.client.login(username='user_b', password='passB1234!')
        url = reverse('careon:budget_detail', kwargs={'pk': self.budget_a.pk})
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_update_cross_org_returns_404(self):
        self.client.login(username='user_b', password='passB1234!')
        url = reverse('careon:budget_update', kwargs={'pk': self.budget_a.pk})
        self.assertEqual(self.client.get(url).status_code, 404)


class CaseIntakeProcessIsolationTest(CrossTenantFixtureMixin, TestCase):
    """CaseIntakeProcess cross-tenant isolation via organization FK (migration 0005)."""

    def setUp(self):
        super().setUp()
        self.dd_a = CaseIntakeProcess.objects.create(
            organization=self.org_a,
            title='Alpha DD', transaction_type='ACQUISITION',
            target_company='Target A',
            start_date=datetime.date.today(),
            target_completion_date=datetime.date.today() + datetime.timedelta(days=90),
            case_coordinator=self.user_a,
        )
        self.dd_b = CaseIntakeProcess.objects.create(
            organization=self.org_b,
            title='Beta DD', transaction_type='MERGER',
            target_company='Target B',
            start_date=datetime.date.today(),
            target_completion_date=datetime.date.today() + datetime.timedelta(days=90),
            case_coordinator=self.user_b,
        )

    def test_list_excludes_other_org(self):
        self.client.login(username='user_b', password='passB1234!')
        response = self.client.get(reverse('careon:intake_list'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('flow=intake', response['Location'])

    def test_detail_cross_org_returns_404(self):
        self.client.login(username='user_b', password='passB1234!')
        url = reverse('careon:intake_detail', kwargs={'pk': self.dd_a.pk})
        self.assertEqual(self.client.get(url).status_code, 302)

    def test_update_cross_org_returns_404(self):
        self.client.login(username='user_b', password='passB1234!')
        url = reverse('careon:intake_update', kwargs={'pk': self.dd_a.pk})
        self.assertEqual(self.client.get(url).status_code, 302)
