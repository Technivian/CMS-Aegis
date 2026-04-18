from html.parser import HTMLParser
from urllib.parse import urlparse

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import Resolver404, resolve, reverse

from contracts.models import Contract, Organization, OrganizationMembership


class _InteractiveElementParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.forms = []
        self.button_actions = []
        self._current_form = None

    def handle_starttag(self, tag, attrs):
        attr_map = dict(attrs)

        if tag == 'a':
            href = attr_map.get('href')
            if href:
                self.links.append(href)
            return

        if tag == 'form':
            self._current_form = {
                'action': attr_map.get('action', ''),
                'method': attr_map.get('method', 'get').lower(),
                'has_csrf': False,
                'submit_controls': 0,
            }
            return

        if self._current_form and tag == 'input':
            input_name = attr_map.get('name', '')
            input_type = attr_map.get('type', '').lower()
            if input_name == 'csrfmiddlewaretoken':
                self._current_form['has_csrf'] = True
            if input_type == 'submit':
                self._current_form['submit_controls'] += 1
            return

        if tag == 'button':
            button_type = attr_map.get('type', 'submit').lower()
            formaction = attr_map.get('formaction')
            if formaction:
                self.button_actions.append(formaction)
            if self._current_form and button_type == 'submit':
                self._current_form['submit_controls'] += 1

    def handle_endtag(self, tag):
        if tag == 'form' and self._current_form:
            self.forms.append(self._current_form)
            self._current_form = None


class UIButtonAndFlowIntegrityTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='uiowner',
            password='testpass123',
            email='uiowner@example.com',
        )
        self.organization = Organization.objects.create(name='UI Test Org', slug='ui-test-org')
        OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.user,
            role=OrganizationMembership.Role.OWNER,
            is_active=True,
        )
        Contract.objects.create(
            organization=self.organization,
            title='UI Integrity Contract',
            content='Contract used for link/form target checks.',
            status=Contract.Status.DRAFT,
            created_by=self.user,
        )
        self.client.login(username='uiowner', password='testpass123')

    def _normalize_internal_path(self, raw_url, current_path):
        if not raw_url:
            return current_path

        parsed = urlparse(raw_url)
        if parsed.scheme or parsed.netloc:
            return None

        if raw_url.startswith(('#', 'javascript:', 'mailto:', 'tel:')):
            return None

        if parsed.path.startswith(('/static/', '/media/')):
            return None

        if not parsed.path:
            return current_path

        return parsed.path

    def _assert_resolves(self, path, source_page, raw_target):
        try:
            resolve(path)
        except Resolver404:
            self.fail(f'Unresolvable target on {source_page}: {raw_target}')

    def test_click_targets_and_forms_are_wired_on_core_pages(self):
        pages = [
            reverse('dashboard'),
            reverse('contracts:contract_list'),
            reverse('contracts:global_search'),
            reverse('contracts:document_list'),
            reverse('contracts:deadline_list'),
            reverse('contracts:legal_task_kanban'),
            reverse('contracts:risk_log_list'),
            reverse('contracts:budget_list'),
            reverse('contracts:trademark_request_list'),
            reverse('contracts:due_diligence_list'),
            reverse('contracts:workflow_dashboard'),
            reverse('contracts:repository'),
            reverse('contracts:reports_dashboard'),
            reverse('contracts:organization_team'),
            reverse('contracts:notification_list'),
            reverse('contracts:privacy_dashboard'),
        ]

        for page in pages:
            response = self.client.get(page)
            self.assertEqual(response.status_code, 200, msg=f'Page failed: {page}')

            parser = _InteractiveElementParser()
            parser.feed(response.content.decode('utf-8'))

            for href in parser.links:
                target_path = self._normalize_internal_path(href, page)
                if not target_path:
                    continue
                self._assert_resolves(target_path, page, href)

            for button_action in parser.button_actions:
                target_path = self._normalize_internal_path(button_action, page)
                if not target_path:
                    continue
                self._assert_resolves(target_path, page, button_action)

            for form in parser.forms:
                action = form['action']
                target_path = self._normalize_internal_path(action, page)
                if target_path:
                    self._assert_resolves(target_path, page, action or '[current-page-action]')

                if form['method'] == 'post' and form['submit_controls'] > 0:
                    self.assertTrue(
                        form['has_csrf'],
                        msg=f'Missing CSRF token in POST form on {page} (action: {action or page})',
                    )

    def test_case_flow_semantics_on_high_traffic_pages(self):
        dashboard_response = self.client.get(reverse('dashboard'))
        self.assertEqual(dashboard_response.status_code, 200)
        self.assertContains(dashboard_response, 'Active Cases')
        self.assertContains(dashboard_response, 'Open Task Signals')
        self.assertContains(dashboard_response, 'Recent Cases')

        list_response = self.client.get(reverse('contracts:contract_list'))
        self.assertEqual(list_response.status_code, 200)
        self.assertContains(list_response, 'Cases')
        self.assertContains(list_response, 'Search cases...')
        self.assertContains(list_response, 'New Case')

        detail_response = self.client.get(reverse('contracts:contract_detail', kwargs={'pk': Contract.objects.first().pk}))
        self.assertEqual(detail_response.status_code, 200)
        self.assertContains(detail_response, 'Case Flow')
        self.assertContains(detail_response, 'Case Details')
        self.assertContains(detail_response, 'Case Actions')

        search_response = self.client.get(reverse('contracts:global_search'), {'q': 'UI Integrity'})
        self.assertEqual(search_response.status_code, 200)
        self.assertContains(search_response, 'Search across cases, case matters, documents, and task signals')
        self.assertContains(search_response, 'Cases (1)')
