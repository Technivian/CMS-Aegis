from html.parser import HTMLParser
from pathlib import Path
import re
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


class _LabelAssociationParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = set()
        self.labels = []
        self._inside_label = False
        self._current_label_for = None
        self._current_label_text = []

    def handle_starttag(self, tag, attrs):
        attr_map = dict(attrs)

        element_id = attr_map.get('id')
        if element_id:
            self.ids.add(element_id)

        if tag == 'label' and attr_map.get('for'):
            self._inside_label = True
            self._current_label_for = attr_map.get('for')
            self._current_label_text = []

    def handle_data(self, data):
        if self._inside_label:
            self._current_label_text.append(data)

    def handle_endtag(self, tag):
        if tag == 'label' and self._inside_label:
            label_text = ' '.join(' '.join(self._current_label_text).split())
            self.labels.append((self._current_label_for, label_text))
            self._inside_label = False
            self._current_label_for = None
            self._current_label_text = []


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
            reverse('careon:case_create'),
            reverse('careon:case_list'),
            reverse('careon:document_list'),
            reverse('careon:deadline_list'),
            reverse('careon:task_list'),
            reverse('careon:signal_list'),
            reverse('careon:budget_list'),
            reverse('careon:placement_list'),
            reverse('careon:intake_list'),
            reverse('careon:workflow_dashboard'),
            reverse('careon:municipality_list'),
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

    def test_labels_reference_real_elements_on_core_pages(self):
        pages = [
            reverse('careon:case_create'),
            reverse('careon:task_create'),
            reverse('careon:signal_create'),
            reverse('careon:assessment_create'),
            reverse('careon:budget_create'),
            reverse('careon:municipality_create'),
            reverse('careon:regional_create'),
        ]

        for page in pages:
            response = self.client.get(page, follow=True)
            self.assertEqual(response.status_code, 200, msg=f'Page failed: {page}')

            parser = _LabelAssociationParser()
            parser.feed(response.content.decode('utf-8'))

            broken_labels = [
                (field_id, label_text)
                for field_id, label_text in parser.labels
                if field_id and field_id not in parser.ids
            ]

            self.assertEqual(
                broken_labels,
                [],
                msg=f'Broken label associations on {page}: {broken_labels}',
            )

    def test_case_create_uses_current_guided_layout_copy(self):
        response = self.client.get(reverse('careon:case_create'), follow=True)
        self.assertEqual(response.status_code, 200)

        # Current approved copy and step treatment for the guided single-page intake.
        self.assertContains(
            response,
            'Start met de intakegegevens. Na opslaan ga je direct naar het casusdossier voor beoordeling en matching.',
        )
        self.assertContains(response, 'Velden met <strong>*</strong> zijn verplicht.')

        # Legacy version should not reappear.
        self.assertNotContains(
            response,
            '4 stappen naar een complete intake binnen de casusflow en direct inzetbare matching.',
        )
        self.assertEqual(response.get('X-Careon-Template-Version'), 'intake_form')
        self.assertNotContains(response, 'UI versie: intake_form_v3')
        self.assertNotContains(response, 'Intakeformulier')
        self.assertNotContains(
            response,
            'Vul de vier blokken hieronder in. Velden met <strong>*</strong> zijn verplicht.',
        )

    def test_case_create_entry_links_stay_versioned(self):
        dashboard_response = self.client.get(reverse('dashboard'), follow=True)
        self.assertEqual(dashboard_response.status_code, 200)
        dashboard_html = dashboard_response.content.decode('utf-8')
        self.assertIn('href="/care/casussen/new/"', dashboard_html)
        self.assertNotIn('/care/casussen/new/?v=', dashboard_html)

        list_response = self.client.get(reverse('careon:case_list'), follow=True)
        self.assertEqual(list_response.status_code, 200)
        list_html = list_response.content.decode('utf-8')
        self.assertIn('href="/care/casussen/new/"', list_html)
        self.assertNotIn('/care/casussen/new/?v=', list_html)

    def test_dashboard_zero_case_primary_action_stays_versioned(self):
        empty_user = User.objects.create_user(
            username='uizero',
            password='testpass123',
            email='uizero@example.com',
        )
        empty_org = Organization.objects.create(name='UI Zero Org', slug='ui-zero-org')
        OrganizationMembership.objects.create(
            organization=empty_org,
            user=empty_user,
            role=OrganizationMembership.Role.OWNER,
            is_active=True,
        )

        self.client.logout()
        self.client.login(username='uizero', password='testpass123')

        response = self.client.get(reverse('dashboard'), follow=True)
        self.assertEqual(response.status_code, 200)
        html = response.content.decode('utf-8')
        self.assertIn('href="/care/casussen/new/"', html)
        self.assertNotIn('/care/casussen/new/?v=', html)

    def test_static_templates_have_matching_label_for_and_id_pairs(self):
        template_root = Path(__file__).resolve().parents[1] / 'theme' / 'templates'
        label_pattern = re.compile(r'<label[^>]*\bfor="([^"]+)"', re.IGNORECASE)
        id_pattern = re.compile(r'\bid="([^"]+)"', re.IGNORECASE)

        violations = []
        for template in template_root.rglob('*.html'):
            content = template.read_text(encoding='utf-8')

            static_labels = [
                field_id
                for field_id in label_pattern.findall(content)
                if '{{' not in field_id and '{%' not in field_id
            ]
            if not static_labels:
                continue

            static_ids = {
                field_id
                for field_id in id_pattern.findall(content)
                if '{{' not in field_id and '{%' not in field_id
            }

            missing_ids = sorted({field_id for field_id in static_labels if field_id not in static_ids})
            if missing_ids:
                relative_path = template.relative_to(Path(__file__).resolve().parents[1])
                for field_id in missing_ids:
                    violations.append(f'{relative_path}: missing id="{field_id}"')

        self.assertEqual(
            violations,
            [],
            msg='Broken static label/id associations found:\n' + '\n'.join(violations),
        )
