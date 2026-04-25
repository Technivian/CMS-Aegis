from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from contracts.models import (
    ApprovalRequest,
    ApprovalRule,
    BackgroundJob,
    ClauseCategory,
    ClausePlaybook,
    ClauseTemplate,
    ClauseVariant,
    Contract,
    Organization,
    OrganizationAPIToken,
    OrganizationMembership,
)
from contracts.services.clause_versions import clone_clause_template_version


User = get_user_model()


class ApiVersionsClausesOperationsSearchTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='owner', email='owner@example.com', password='testpass123')
        self.organization = Organization.objects.create(name='API Org', slug='api-org', require_mfa=False)
        OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.user,
            role=OrganizationMembership.Role.OWNER,
            is_active=True,
        )
        self.profile = getattr(self.user, 'profile', None)
        self.client.login(username='owner', password='testpass123')

    def test_versioned_contract_api_uses_scoped_token(self):
        contract = Contract.objects.create(
            organization=self.organization,
            title='API Contract',
            counterparty='Acme',
            content='Agreement body',
            status=Contract.Status.DRAFT,
        )
        api_token_record, raw_token = OrganizationAPIToken.create_token(
            organization=self.organization,
            scopes=['contracts:read'],
            label='Read token',
            created_by=self.user,
        )

        response = self.client.get(
            reverse('contracts:contracts_api_v1'),
            HTTP_AUTHORIZATION=f'Bearer {raw_token}',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['X-API-Version'], '1')
        payload = response.json()
        self.assertEqual(payload['meta']['organization'], self.organization.slug)
        self.assertEqual(payload['meta']['token_label'], api_token_record.label)
        self.assertEqual(payload['data']['total_count'], 1)
        self.assertEqual(payload['data']['contracts'][0]['title'], contract.title)

    def test_versioned_contract_api_rejects_wrong_scope(self):
        OrganizationAPIToken.create_token(
            organization=self.organization,
            scopes=['privacy:read'],
            label='Privacy token',
            created_by=self.user,
        )
        token = self.organization.rotate_api_token(scopes=['privacy:read'], created_by=self.user)[1]

        response = self.client.get(
            reverse('contracts:contracts_api_v1'),
            HTTP_AUTHORIZATION=f'Bearer {token}',
        )

        self.assertEqual(response.status_code, 401)

    def test_clause_variant_resolution_prefers_matching_variant(self):
        category = ClauseCategory.objects.create(organization=self.organization, name='General', description='')
        template = ClauseTemplate.objects.create(
            organization=self.organization,
            title='Data Protection',
            category=category,
            content='Standard clause',
            fallback_content='Template fallback',
            jurisdiction_scope=ClauseTemplate.JurisdictionScope.GLOBAL,
            applicable_contract_types='MSA',
            playbook_notes='Template notes',
            tags='privacy, data',
        )
        playbook = ClausePlaybook.objects.create(
            organization=self.organization,
            name='EU Privacy Playbook',
            fallback_position='Use local DPA language',
            jurisdiction_scope=ClausePlaybook.JurisdictionScope.EU,
            risk_level='HIGH',
        )
        variant = ClauseVariant.objects.create(
            organization=self.organization,
            template=template,
            playbook=playbook,
            jurisdiction_scope=ClauseTemplate.JurisdictionScope.EU,
            contract_type='MSA',
            risk_level='HIGH',
            fallback_content='EU fallback',
            playbook_notes='EU negotiation notes',
            priority=10,
        )
        contract = Contract.objects.create(
            organization=self.organization,
            title='MSA',
            counterparty='Beta',
            content='Agreement body',
            contract_type='MSA',
            jurisdiction='Netherlands',
            governing_law='EU',
            risk_level='HIGH',
        )

        self.assertEqual(variant.template_id, template.id)
        response = self.client.get(reverse('contracts:clause_template_detail', kwargs={'pk': template.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Resolved playbook', html=False)
        self.assertContains(response, 'EU Privacy Playbook', html=False)
        self.assertContains(response, 'EU fallback', html=False)
        self.assertContains(response, 'EU negotiation notes', html=False)
        self.assertContains(response, 'Create variant', html=False)
        self.assertContains(response, 'Create playbook', html=False)

    def test_clause_variant_create_action_adds_variant(self):
        category = ClauseCategory.objects.create(organization=self.organization, name='General', description='')
        template = ClauseTemplate.objects.create(
            organization=self.organization,
            title='Security Clause',
            category=category,
            content='Standard content',
            fallback_content='Template fallback',
            jurisdiction_scope=ClauseTemplate.JurisdictionScope.GLOBAL,
            applicable_contract_types='MSA',
            playbook_notes='Template notes',
            tags='security',
        )
        playbook = ClausePlaybook.objects.create(
            organization=self.organization,
            name='Security Playbook',
            fallback_position='Use fallback',
            jurisdiction_scope=ClausePlaybook.JurisdictionScope.GLOBAL,
            risk_level='MEDIUM',
        )

        response = self.client.post(
            reverse('contracts:clause_variant_create', kwargs={'pk': template.pk}),
            data={
                'playbook': playbook.pk,
                'jurisdiction_scope': ClauseTemplate.JurisdictionScope.GLOBAL,
                'contract_type': 'MSA',
                'risk_level': 'MEDIUM',
                'fallback_content': 'Negotiated fallback',
                'playbook_notes': 'Use this when customer objects',
                'priority': 5,
                'is_active': 'on',
            },
        )

        self.assertEqual(response.status_code, 302)
        variant = ClauseVariant.objects.get(template=template, playbook=playbook)
        self.assertEqual(variant.fallback_content, 'Negotiated fallback')
        self.assertEqual(variant.priority, 5)
        self.assertTrue(variant.is_active)

    def test_clause_playbook_create_action_adds_playbook(self):
        category = ClauseCategory.objects.create(organization=self.organization, name='General', description='')
        template = ClauseTemplate.objects.create(
            organization=self.organization,
            title='Confidentiality',
            category=category,
            content='Base text',
            fallback_content='Fallback',
            jurisdiction_scope=ClauseTemplate.JurisdictionScope.GLOBAL,
            tags='confidentiality',
        )

        response = self.client.post(
            reverse('contracts:clause_playbook_create', kwargs={'pk': template.pk}),
            data={
                'name': 'Confidentiality Playbook',
                'description': 'Guidance for confidentiality clauses',
                'fallback_position': 'Prefer stronger protections',
                'jurisdiction_scope': ClausePlaybook.JurisdictionScope.GLOBAL,
                'risk_level': 'LOW',
                'is_active': 'on',
            },
        )

        self.assertEqual(response.status_code, 302)
        playbook = ClausePlaybook.objects.get(name='Confidentiality Playbook')
        self.assertEqual(playbook.description, 'Guidance for confidentiality clauses')
        self.assertTrue(playbook.is_active)

    def test_clause_template_update_creates_immutable_version_and_copies_variants(self):
        category = ClauseCategory.objects.create(organization=self.organization, name='General', description='')
        template = ClauseTemplate.objects.create(
            organization=self.organization,
            title='Data Protection',
            category=category,
            content='Original clause text',
            fallback_content='Original fallback',
            jurisdiction_scope=ClauseTemplate.JurisdictionScope.GLOBAL,
            applicable_contract_types='MSA',
            playbook_notes='Original notes',
            tags='privacy',
        )
        playbook = ClausePlaybook.objects.create(
            organization=self.organization,
            name='Privacy Playbook',
            fallback_position='Fallback',
            jurisdiction_scope=ClausePlaybook.JurisdictionScope.GLOBAL,
            risk_level='MEDIUM',
        )
        ClauseVariant.objects.create(
            organization=self.organization,
            template=template,
            playbook=playbook,
            jurisdiction_scope=ClauseTemplate.JurisdictionScope.GLOBAL,
            contract_type='MSA',
            risk_level='MEDIUM',
            fallback_content='Variant fallback',
            playbook_notes='Variant notes',
            priority=10,
        )

        response = self.client.post(
            reverse('contracts:clause_template_update', kwargs={'pk': template.pk}),
            data={
                'title': 'Data Protection Revised',
                'category': category.pk,
                'content': 'Revised clause text',
                'fallback_content': 'Revised fallback',
                'jurisdiction_scope': ClauseTemplate.JurisdictionScope.EU,
                'is_mandatory': 'on',
                'applicable_contract_types': 'MSA, SOW',
                'playbook_notes': 'Revised notes',
                'tags': 'privacy, revised',
            },
        )

        self.assertEqual(response.status_code, 302)
        new_version = ClauseTemplate.objects.get(parent_template=template)
        self.assertEqual(new_version.version, 2)
        self.assertEqual(new_version.title, 'Data Protection Revised')
        self.assertEqual(new_version.content, 'Revised clause text')
        self.assertEqual(new_version.fallback_content, 'Revised fallback')
        self.assertTrue(new_version.is_mandatory)
        self.assertEqual(new_version.applicable_contract_types, 'MSA, SOW')
        self.assertEqual(new_version.playbook_notes, 'Revised notes')
        self.assertEqual(new_version.tags, 'privacy, revised')
        self.assertEqual(new_version.variants.count(), 1)
        self.assertEqual(new_version.variants.first().playbook_id, playbook.id)
        self.assertEqual(template.version, 1)
        self.assertEqual(template.title, 'Data Protection')
        self.assertEqual(template.content, 'Original clause text')

    def test_clause_template_compare_shows_version_differences(self):
        category = ClauseCategory.objects.create(organization=self.organization, name='General', description='')
        template = ClauseTemplate.objects.create(
            organization=self.organization,
            title='Security Clause',
            category=category,
            content='Base content',
            fallback_content='Base fallback',
            jurisdiction_scope=ClauseTemplate.JurisdictionScope.GLOBAL,
            applicable_contract_types='MSA',
            playbook_notes='Base notes',
            tags='security',
        )
        compare_version = clone_clause_template_version(
            template,
            title='Security Clause Revised',
            content='Revised content',
            fallback_content='Revised fallback',
            jurisdiction_scope=ClauseTemplate.JurisdictionScope.EU,
            playbook_notes='Revised notes',
            tags='security, revised',
        )

        response = self.client.get(
            reverse('contracts:clause_template_compare', kwargs={'pk': compare_version.pk, 'other_pk': template.pk}),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Field differences', html=False)
        self.assertContains(response, 'content', html=False)
        self.assertContains(response, 'Base content', html=False)
        self.assertContains(response, 'Revised content', html=False)
        self.assertContains(response, 'Variant differences', html=False)
        self.assertContains(response, 'Security Clause Revised', html=False)

    def test_approval_request_delegation_updates_assignee(self):
        delegate = User.objects.create_user(username='delegate', email='delegate@example.com', password='testpass123')
        OrganizationMembership.objects.create(
            organization=self.organization,
            user=delegate,
            role=OrganizationMembership.Role.ADMIN,
            is_active=True,
        )
        contract = Contract.objects.create(
            organization=self.organization,
            title='Delegation Contract',
            counterparty='Acme',
            content='Body',
            status=Contract.Status.DRAFT,
        )
        approval = ApprovalRequest.objects.create(
            organization=self.organization,
            contract=contract,
            approval_step='LEGAL',
            status=ApprovalRequest.Status.PENDING,
            assigned_to=self.user,
            due_date=timezone.now() + timedelta(days=2),
        )

        response = self.client.post(
            reverse('contracts:approval_request_update', kwargs={'pk': approval.pk}),
            data={
                'contract': contract.pk,
                'approval_step': 'LEGAL',
                'status': ApprovalRequest.Status.PENDING,
                'assigned_to': self.user.pk,
                'delegated_to': delegate.pk,
                'comments': 'Delegating to colleague',
                'due_date': (timezone.now() + timedelta(days=2)).strftime('%Y-%m-%dT%H:%M'),
            },
        )

        self.assertEqual(response.status_code, 302)
        approval.refresh_from_db()
        self.assertEqual(approval.assigned_to_id, delegate.id)
        self.assertEqual(approval.delegated_to_id, delegate.id)
        self.assertIsNotNone(approval.delegated_at)

    def test_global_search_ranks_exact_matches_and_honors_type_filters(self):
        exact = Contract.objects.create(
            organization=self.organization,
            title='Alpha Contract',
            counterparty='Exact',
            content='Body',
            status=Contract.Status.DRAFT,
        )
        partial = Contract.objects.create(
            organization=self.organization,
            title='Contract Alpha',
            counterparty='Partial',
            content='Body',
            status=Contract.Status.DRAFT,
        )

        response = self.client.get(reverse('contracts:global_search'), {'q': 'Alpha', 'type': 'contract'})
        self.assertEqual(response.status_code, 200)
        contract_results = response.context['results']['contracts']
        self.assertEqual(contract_results[0].title, exact.title)
        self.assertIn(partial.title, [item.title for item in contract_results])

    def test_global_search_semantic_clause_mode_matches_synonyms(self):
        category = ClauseCategory.objects.create(organization=self.organization, name='Risk Clauses')
        semantic_clause = ClauseTemplate.objects.create(
            organization=self.organization,
            title='NDA Confidentiality Covenant',
            category=category,
            content='Each party must protect trade secrets and confidential information.',
            tags='nda, confidentiality',
            created_by=self.user,
        )
        ClauseTemplate.objects.create(
            organization=self.organization,
            title='Payment Terms',
            category=category,
            content='Invoices are due in thirty days.',
            tags='finance',
            created_by=self.user,
        )

        response = self.client.get(
            reverse('contracts:global_search'),
            {'q': 'non disclosure obligations', 'type': 'clause', 'search_mode': 'semantic'},
        )

        self.assertEqual(response.status_code, 200)
        clause_results = response.context['results']['clauses']
        self.assertGreaterEqual(len(clause_results), 1)
        self.assertEqual(clause_results[0].id, semantic_clause.id)

    def test_global_search_keyword_clause_mode_does_not_use_semantic_expansion(self):
        category = ClauseCategory.objects.create(organization=self.organization, name='Risk Clauses')
        ClauseTemplate.objects.create(
            organization=self.organization,
            title='NDA Confidentiality Covenant',
            category=category,
            content='Each party must protect trade secrets and confidential information.',
            tags='nda, confidentiality',
            created_by=self.user,
        )

        response = self.client.get(
            reverse('contracts:global_search'),
            {'q': 'non disclosure obligations', 'type': 'clause', 'search_mode': 'keyword'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context['results']['clauses']), [])

    def test_operations_dashboard_and_drill_command(self):
        BackgroundJob.objects.create(
            organization=self.organization,
            job_type='send_contract_reminders',
            payload={},
        )

        response = self.client.get(reverse('operations_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Operations Dashboard', html=False)

        cache.delete('operations_drill.last_run_iso')
        self.assertIsNone(cache.get('operations_drill.last_run_iso'))
        from django.core.management import call_command

        call_command('run_operational_drill')
        self.assertIsNotNone(cache.get('operations_drill.last_run_iso'))
