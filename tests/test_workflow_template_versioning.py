from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from contracts.models import Contract, Organization, OrganizationMembership, Workflow, WorkflowTemplate, WorkflowTemplateStep
from contracts.services.workflow_templates import clone_template_version, list_template_versions


User = get_user_model()


class WorkflowTemplateVersioningTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='template-user', password='pass12345')
        self.org = Organization.objects.create(name='Template Org', slug='template-org')
        OrganizationMembership.objects.create(
            organization=self.org,
            user=self.user,
            role=OrganizationMembership.Role.OWNER,
            is_active=True,
        )
        self.contract = Contract.objects.create(
            organization=self.org,
            title='Template Contract',
            content='Template content',
            status=Contract.Status.ACTIVE,
            created_by=self.user,
        )
        self.template = WorkflowTemplate.objects.create(
            name='Contract Review',
            description='Base contract review flow',
            category=WorkflowTemplate.Category.CONTRACT_REVIEW,
            version=1,
            is_active=True,
        )
        self.alt_template = WorkflowTemplate.objects.create(
            name='Compliance Review',
            description='Alternate flow',
            category=WorkflowTemplate.Category.COMPLIANCE,
            version=1,
            is_active=True,
        )
        WorkflowTemplateStep.objects.create(
            template=self.template,
            name='Intake',
            description='Initial intake',
            order=1,
        )
        WorkflowTemplateStep.objects.create(
            template=self.template,
            name='Review',
            description='Legal review',
            order=2,
        )
        self.workflow = Workflow.objects.create(
            organization=self.org,
            title='Workflow One',
            description='First workflow',
            contract=self.contract,
            template=self.template,
            created_by=self.user,
        )

    def test_clone_template_version_copies_steps_and_links_lineage(self):
        clone = clone_template_version(self.template, name='Contract Review v2')

        self.assertEqual(clone.version, 2)
        self.assertEqual(clone.parent_template_id, self.template.id)
        self.assertEqual(clone.name, 'Contract Review v2')
        self.assertEqual(clone.steps.count(), 2)
        self.assertEqual(clone.steps.first().name, 'Intake')

    def test_list_template_versions_returns_latest_first(self):
        clone = clone_template_version(self.template)
        versions = list_template_versions(clone)

        self.assertGreaterEqual(len(versions), 2)
        self.assertEqual(versions[0].version, 2)
        self.assertEqual(versions[1].version, 1)

    def test_management_command_clones_and_migrates_workflows(self):
        call_command(
            'migrate_workflow_template',
            source_template_id=self.template.id,
            migrate_workflows=True,
            deactivate_source=True,
        )

        refreshed_workflow = Workflow.objects.get(pk=self.workflow.pk)
        new_template = refreshed_workflow.template
        self.assertNotEqual(new_template.pk, self.template.pk)
        self.assertEqual(new_template.version, 2)
        self.assertEqual(new_template.parent_template_id, self.template.id)

        self.template.refresh_from_db()
        self.assertFalse(self.template.is_active)

    def test_template_views_render_version_and_steps(self):
        self.client.force_login(self.user)

        list_response = self.client.get(reverse('contracts:workflow_template_list'))
        self.assertEqual(list_response.status_code, 200)
        self.assertContains(list_response, 'v1')
        self.assertContains(list_response, 'Intake')

        detail_response = self.client.get(reverse('contracts:workflow_template_detail', args=[self.template.pk]))
        self.assertEqual(detail_response.status_code, 200)
        self.assertContains(detail_response, 'v1')
        self.assertContains(detail_response, 'Workflow Steps')
        self.assertContains(detail_response, 'Add a step')

    def test_template_detail_add_step_creates_step_and_redirects(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse('contracts:workflow_template_step_add', args=[self.template.pk]),
            data={
                'name': 'Signature',
                'description': 'Collect signatures',
                'order': '3',
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(
            response,
            reverse('contracts:workflow_template_detail', args=[self.template.pk]),
            fetch_redirect_response=False,
        )

        self.template.refresh_from_db()
        created_step = WorkflowTemplateStep.objects.get(template=self.template, name='Signature')
        self.assertEqual(created_step.description, 'Collect signatures')
        self.assertEqual(created_step.order, 3)

    def test_template_detail_clone_action_creates_new_version(self):
        self.client.force_login(self.user)

        response = self.client.post(reverse('contracts:workflow_template_clone_version', args=[self.template.pk]))
        self.assertEqual(response.status_code, 302)

        clone = WorkflowTemplate.objects.get(version=2)
        self.assertEqual(clone.parent_template_id, self.template.id)
        self.assertEqual(clone.steps.count(), 2)
        self.assertRedirects(response, reverse('contracts:workflow_template_detail', args=[clone.pk]), fetch_redirect_response=False)

    def test_template_restore_action_creates_follow_on_version(self):
        self.client.force_login(self.user)
        clone = clone_template_version(self.template)

        response = self.client.post(reverse('contracts:workflow_template_restore_version', args=[self.template.pk]))
        self.assertEqual(response.status_code, 302)

        restored = WorkflowTemplate.objects.get(version=3)
        self.assertEqual(restored.parent_template_id, self.template.id)
        self.assertEqual(restored.steps.count(), 2)
        self.assertRedirects(response, reverse('contracts:workflow_template_detail', args=[restored.pk]), fetch_redirect_response=False)

    def test_template_compare_view_shows_field_and_step_differences(self):
        self.client.force_login(self.user)
        clone = clone_template_version(self.template, name='Contract Review Revised')
        clone.description = 'Changed flow'
        clone.save(update_fields=['description'])

        response = self.client.get(reverse('contracts:workflow_template_compare', args=[self.template.pk, clone.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Template Comparison')
        self.assertContains(response, 'Field Differences')
        self.assertContains(response, 'name')

    def test_template_compare_view_supports_legal_ops_preset(self):
        self.client.force_login(self.user)
        clone = clone_template_version(self.template, name='Contract Review Revised')
        clone.description = 'Changed flow'
        clone.save(update_fields=['description'])

        response = self.client.get(
            reverse('contracts:workflow_template_compare', args=[self.template.pk, clone.pk]) + '?preset=legal_ops'
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Legal ops review')
        self.assertNotContains(response, 'description')

    def test_workflow_editor_surfaces_suggested_template_summary(self):
        self.client.force_login(self.user)
        request_url = reverse('contracts:workflow_create')
        response = self.client.get(
            f"{request_url}?contract_pk={self.contract.pk}&template_pk={self.alt_template.pk}"
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Suggested template')
        self.assertContains(response, 'Compare against selected template')
        self.assertContains(response, 'Open legal ops diff')
