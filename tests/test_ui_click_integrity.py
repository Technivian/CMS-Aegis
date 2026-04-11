from html.parser import HTMLParser
from urllib.parse import urlparse

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import Resolver404, resolve, reverse

from contracts.models import CareCase, Organization, OrganizationMembership


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
        CareCase.objects.create(
            organization=self.organization,
            title='UI Integrity Case',
            content='Case used for link/form target checks.',
            status=CareCase.Status.DRAFT,
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
            reverse('careon:case_list'),
            reverse('careon:document_list'),
            reverse('careon:deadline_list'),
            reverse('careon:task_list'),
            reverse('careon:signal_list'),
            reverse('careon:budget_list'),
            reverse('careon:placement_list'),
            reverse('careon:intake_list'),
            reverse('careon:workflow_dashboard'),
            reverse('careon:configuration_list'),
            reverse('careon:reports_dashboard'),
            reverse('careon:organization_team'),
            reverse('careon:notification_list'),
        ]

        for page in pages:
            response = self.client.get(page, follow=True)
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
