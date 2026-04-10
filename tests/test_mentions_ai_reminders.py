from datetime import timedelta
import json

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from contracts.models import (
    ChecklistItem,
    ComplianceChecklist,
    Contract,
    Deadline,
    Document,
    LegalTask,
    NegotiationThread,
    Notification,
    Organization,
    OrganizationMembership,
    RiskLog,
    Workflow,
    WorkflowStep,
)


class MentionsAiAndReminderTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username='owner',
            email='owner@example.com',
            password='testpass123',
        )
        self.member = User.objects.create_user(
            username='member',
            email='member@example.com',
            password='testpass123',
        )
        self.admin = User.objects.create_user(
            username='adminuser',
            email='admin@example.com',
            password='testpass123',
        )
        self.member_creator = User.objects.create_user(
            username='membercreator',
            email='membercreator@example.com',
            password='testpass123',
        )
        self.outsider = User.objects.create_user(
            username='outsider',
            email='outsider@example.com',
            password='testpass123',
        )

        self.organization = Organization.objects.create(name='Acme Firm', slug='acme-firm-main')
        self.other_organization = Organization.objects.create(name='Other Firm', slug='other-firm')

        OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.owner,
            role=OrganizationMembership.Role.OWNER,
            is_active=True,
        )
        OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.member,
            role=OrganizationMembership.Role.MEMBER,
            is_active=True,
        )
        OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.admin,
            role=OrganizationMembership.Role.ADMIN,
            is_active=True,
        )
        OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.member_creator,
            role=OrganizationMembership.Role.MEMBER,
            is_active=True,
        )
        OrganizationMembership.objects.create(
            organization=self.other_organization,
            user=self.outsider,
            role=OrganizationMembership.Role.OWNER,
            is_active=True,
        )

        self.contract = Contract.objects.create(
            organization=self.organization,
            title='Master Services Agreement',
            contract_type=Contract.ContractType.MSA,
            status=Contract.Status.ACTIVE,
            risk_level=Contract.RiskLevel.HIGH,
            content='Primary terms and obligations.',
            created_by=self.owner,
            end_date=timezone.localdate() + timedelta(days=7),
            renewal_date=timezone.localdate() + timedelta(days=14),
            auto_renew=True,
        )
        self.member_created_contract = Contract.objects.create(
            organization=self.organization,
            title='Member Owned NDA',
            contract_type=Contract.ContractType.NDA,
            status=Contract.Status.DRAFT,
            created_by=self.member_creator,
        )
        self.deadline = Deadline.objects.create(
            title='Contract review checkpoint',
            due_date=timezone.localdate() + timedelta(days=5),
            contract=self.contract,
            created_by=self.owner,
        )
        self.checklist = ComplianceChecklist.objects.create(
            title='Contract compliance gate',
            description='Checklist linked to contract',
            regulation_type=ComplianceChecklist.RegulationType.GDPR,
            contract=self.contract,
            created_by=self.owner,
        )
        self.checklist_item = ChecklistItem.objects.create(
            checklist=self.checklist,
            title='Verify data transfer clauses',
            description='Ensure DPA/SCC references are present.',
            is_completed=False,
            order=1,
        )
        self.workflow = Workflow.objects.create(
            organization=self.organization,
            title='Contract approval workflow',
            description='Workflow linked to contract',
            contract=self.contract,
            created_by=self.owner,
        )
        self.workflow_step = WorkflowStep.objects.create(
            workflow=self.workflow,
            name='Legal signoff',
            description='Complete legal review and signoff.',
            status=WorkflowStep.Status.PENDING,
            order=1,
        )
        self.risk_log = RiskLog.objects.create(
            title='Data transfer compliance risk',
            description='Potential non-compliance if SCCs are missing.',
            risk_level=RiskLog.RiskLevel.HIGH,
            contract=self.contract,
            created_by=self.owner,
        )
        self.legal_task = LegalTask.objects.create(
            title='Finalize execution package',
            description='Collect signatures and archive final PDFs.',
            priority=LegalTask.Priority.HIGH,
            due_date=timezone.localdate() + timedelta(days=10),
            contract=self.contract,
            assigned_to=self.owner,
        )

    def test_mentions_create_notifications_for_org_members_only(self):
        self.client.login(username='owner', password='testpass123')

        response = self.client.post(
            reverse('contracts:add_negotiation_note', kwargs={'pk': self.contract.id}),
            {
                'title': 'Round 1 comments',
                'content': 'Please review this @member and @outsider. @member can take clause 4.',
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(NegotiationThread.objects.filter(contract=self.contract, title='Round 1 comments').exists())
        self.assertEqual(
            Notification.objects.filter(recipient=self.member, notification_type=Notification.NotificationType.CONTRACT).count(),
            1,
        )
        self.assertEqual(Notification.objects.filter(recipient=self.outsider).count(), 0)

    def test_internal_ai_assistant_returns_json_for_authorized_user(self):
        self.client.login(username='owner', password='testpass123')

        response = self.client.post(
            reverse('contracts:contract_ai_assistant', kwargs={'pk': self.contract.id}),
            data=json.dumps({'prompt': 'Give me risk and renewal analysis'}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['ok'])
        self.assertEqual(payload['response']['mode'], 'internal-rules-engine')
        self.assertIn('recommendations', payload['response'])

    def test_internal_ai_assistant_is_scoped_by_tenant(self):
        self.client.login(username='outsider', password='testpass123')

        response = self.client.post(
            reverse('contracts:contract_ai_assistant', kwargs={'pk': self.contract.id}),
            data=json.dumps({'prompt': 'show summary'}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 404)

    def test_contract_update_requires_owner_admin_or_creator(self):
        self.client.login(username='member', password='testpass123')

        response = self.client.get(
            reverse('contracts:contract_update', kwargs={'pk': self.contract.id}),
        )

        self.assertEqual(response.status_code, 403)

    def test_contract_update_allows_admin(self):
        self.client.login(username='adminuser', password='testpass123')

        response = self.client.get(
            reverse('contracts:contract_update', kwargs={'pk': self.contract.id}),
        )

        self.assertEqual(response.status_code, 200)

    def test_contract_update_allows_owner(self):
        self.client.login(username='owner', password='testpass123')

        response = self.client.get(
            reverse('contracts:contract_update', kwargs={'pk': self.contract.id}),
        )

        self.assertEqual(response.status_code, 200)

    def test_contract_update_allows_member_creator(self):
        self.client.login(username='membercreator', password='testpass123')

        response = self.client.get(
            reverse('contracts:contract_update', kwargs={'pk': self.member_created_contract.id}),
        )

        self.assertEqual(response.status_code, 200)

    def test_contract_comment_allows_member(self):
        self.client.login(username='member', password='testpass123')

        response = self.client.post(
            reverse('contracts:add_negotiation_note', kwargs={'pk': self.contract.id}),
            {
                'title': 'Member comment',
                'content': 'Member can comment on in-org contracts.',
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            NegotiationThread.objects.filter(contract=self.contract, title='Member comment').exists()
        )

    def test_contract_comment_blocks_outsider(self):
        self.client.login(username='outsider', password='testpass123')

        response = self.client.post(
            reverse('contracts:add_negotiation_note', kwargs={'pk': self.contract.id}),
            {
                'title': 'Cross-org comment',
                'content': 'This should never land.',
            },
        )

        self.assertEqual(response.status_code, 404)
        self.assertFalse(
            NegotiationThread.objects.filter(contract=self.contract, title='Cross-org comment').exists()
        )

    def test_document_create_requires_contract_edit_permission(self):
        self.client.login(username='member', password='testpass123')

        response = self.client.post(
            reverse('contracts:document_create'),
            {
                'title': 'Unapproved upload',
                'document_type': 'CONTRACT',
                'status': 'DRAFT',
                'contract': self.contract.id,
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(Document.objects.filter(title='Unapproved upload').exists())

    def test_document_create_allows_admin_for_contract(self):
        self.client.login(username='adminuser', password='testpass123')

        response = self.client.post(
            reverse('contracts:document_create'),
            {
                'title': 'Approved upload',
                'document_type': 'CONTRACT',
                'status': 'DRAFT',
                'contract': self.contract.id,
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(Document.objects.filter(title='Approved upload').exists())

    def test_deadline_update_requires_contract_edit_permission(self):
        self.client.login(username='member', password='testpass123')

        response = self.client.get(
            reverse('contracts:deadline_update', kwargs={'pk': self.deadline.id}),
        )

        self.assertEqual(response.status_code, 403)

    def test_deadline_complete_requires_contract_edit_permission(self):
        self.client.login(username='member', password='testpass123')

        response = self.client.post(
            reverse('contracts:deadline_complete', kwargs={'pk': self.deadline.id}),
        )

        self.assertEqual(response.status_code, 403)
        self.deadline.refresh_from_db()
        self.assertFalse(self.deadline.is_completed)

    def test_deadline_complete_allows_admin_for_contract(self):
        self.client.login(username='adminuser', password='testpass123')

        response = self.client.post(
            reverse('contracts:deadline_complete', kwargs={'pk': self.deadline.id}),
        )

        self.assertEqual(response.status_code, 302)
        self.deadline.refresh_from_db()
        self.assertTrue(self.deadline.is_completed)

    def test_toggle_checklist_item_requires_contract_edit_permission(self):
        self.client.login(username='member', password='testpass123')

        response = self.client.post(
            reverse('contracts:toggle_checklist_item', kwargs={'pk': self.checklist_item.id}),
        )

        self.assertEqual(response.status_code, 403)
        self.checklist_item.refresh_from_db()
        self.assertFalse(self.checklist_item.is_completed)

    def test_toggle_checklist_item_allows_admin(self):
        self.client.login(username='adminuser', password='testpass123')

        response = self.client.post(
            reverse('contracts:toggle_checklist_item', kwargs={'pk': self.checklist_item.id}),
        )

        self.assertEqual(response.status_code, 302)
        self.checklist_item.refresh_from_db()
        self.assertTrue(self.checklist_item.is_completed)

    def test_add_checklist_item_requires_contract_edit_permission(self):
        self.client.login(username='member', password='testpass123')

        response = self.client.post(
            reverse('contracts:add_checklist_item', kwargs={'pk': self.checklist.id}),
            {
                'title': 'Unauthorized checklist insert',
                'description': 'Should fail for member.',
                'order': 2,
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(ChecklistItem.objects.filter(title='Unauthorized checklist insert').exists())

    def test_workflow_step_update_requires_contract_edit_permission(self):
        self.client.login(username='member', password='testpass123')

        response = self.client.post(
            reverse('contracts:update_workflow_step', kwargs={'pk': self.workflow_step.id}),
            {'status': WorkflowStep.Status.COMPLETED},
        )

        self.assertEqual(response.status_code, 403)
        self.workflow_step.refresh_from_db()
        self.assertEqual(self.workflow_step.status, WorkflowStep.Status.PENDING)

    def test_workflow_step_update_allows_admin(self):
        self.client.login(username='adminuser', password='testpass123')

        response = self.client.post(
            reverse('contracts:update_workflow_step', kwargs={'pk': self.workflow_step.id}),
            {'status': WorkflowStep.Status.COMPLETED},
        )

        self.assertEqual(response.status_code, 302)
        self.workflow_step.refresh_from_db()
        self.assertEqual(self.workflow_step.status, WorkflowStep.Status.COMPLETED)

    def test_workflow_create_requires_contract_edit_permission(self):
        self.client.login(username='member', password='testpass123')

        response = self.client.post(
            reverse('contracts:workflow_create'),
            {
                'title': 'Unauthorized workflow',
                'description': 'Should fail for member on owner-created contract.',
                'contract': self.contract.id,
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(Workflow.objects.filter(title='Unauthorized workflow').exists())

    def test_risk_log_create_requires_contract_edit_permission(self):
        self.client.login(username='member', password='testpass123')

        response = self.client.post(
            reverse('contracts:risk_log_create'),
            {
                'title': 'Unauthorized risk log',
                'description': 'Should fail for member.',
                'risk_level': RiskLog.RiskLevel.HIGH,
                'contract': self.contract.id,
                'mitigation_plan': 'Draft mitigation plan.',
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(RiskLog.objects.filter(title='Unauthorized risk log').exists())

    def test_risk_log_update_requires_contract_edit_permission(self):
        self.client.login(username='member', password='testpass123')

        response = self.client.get(
            reverse('contracts:risk_log_update', kwargs={'pk': self.risk_log.id}),
        )

        self.assertEqual(response.status_code, 403)

    def test_risk_log_update_allows_admin(self):
        self.client.login(username='adminuser', password='testpass123')

        response = self.client.get(
            reverse('contracts:risk_log_update', kwargs={'pk': self.risk_log.id}),
        )

        self.assertEqual(response.status_code, 200)

    def test_risk_log_list_renders_real_fields(self):
        self.client.login(username='owner', password='testpass123')

        response = self.client.get(reverse('contracts:risk_log_list'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Risk Log')
        self.assertContains(response, 'Data transfer compliance risk')
        self.assertContains(response, 'Master Services Agreement')
        self.assertContains(response, 'No mitigation plan recorded')

    def test_risk_log_list_filters_by_search_and_level(self):
        self.client.login(username='owner', password='testpass123')
        RiskLog.objects.create(
            title='Low-priority admin risk',
            description='Operational cleanup item.',
            risk_level=RiskLog.RiskLevel.LOW,
            contract=self.contract,
            created_by=self.owner,
        )

        response = self.client.get(
            reverse('contracts:risk_log_list'),
            {'q': 'data transfer', 'risk_level': RiskLog.RiskLevel.HIGH},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Data transfer compliance risk')
        self.assertNotContains(response, 'Low-priority admin risk')

    def test_legal_task_create_requires_contract_edit_permission(self):
        self.client.login(username='member', password='testpass123')

        response = self.client.post(
            reverse('contracts:legal_task_create'),
            {
                'title': 'Unauthorized legal task',
                'description': 'Should fail for member.',
                'priority': LegalTask.Priority.MEDIUM,
                'due_date': (timezone.localdate() + timedelta(days=12)).isoformat(),
                'contract': self.contract.id,
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(LegalTask.objects.filter(title='Unauthorized legal task').exists())

    def test_legal_task_update_requires_contract_edit_permission(self):
        self.client.login(username='member', password='testpass123')

        response = self.client.get(
            reverse('contracts:legal_task_update', kwargs={'pk': self.legal_task.id}),
        )

        self.assertEqual(response.status_code, 403)

    def test_legal_task_update_allows_admin(self):
        self.client.login(username='adminuser', password='testpass123')

        response = self.client.get(
            reverse('contracts:legal_task_update', kwargs={'pk': self.legal_task.id}),
        )

        self.assertEqual(response.status_code, 200)

    def test_compliance_checklist_create_requires_contract_edit_permission(self):
        self.client.login(username='member', password='testpass123')

        response = self.client.post(
            reverse('contracts:compliance_checklist_create'),
            {
                'title': 'Unauthorized checklist',
                'description': 'Should fail for member.',
                'regulation_type': ComplianceChecklist.RegulationType.GDPR,
                'contract': self.contract.id,
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(ComplianceChecklist.objects.filter(title='Unauthorized checklist').exists())

    def test_compliance_checklist_update_requires_contract_edit_permission(self):
        self.client.login(username='member', password='testpass123')

        response = self.client.get(
            reverse('contracts:compliance_checklist_update', kwargs={'pk': self.checklist.id}),
        )

        self.assertEqual(response.status_code, 403)

    def test_compliance_checklist_update_allows_admin(self):
        self.client.login(username='adminuser', password='testpass123')

        response = self.client.get(
            reverse('contracts:compliance_checklist_update', kwargs={'pk': self.checklist.id}),
        )

        self.assertEqual(response.status_code, 200)

    def test_contract_reminder_command_creates_and_deduplicates_notifications(self):
        call_command('send_contract_reminders')

        owner_notifications = Notification.objects.filter(recipient=self.owner, title__icontains='reminder')
        admin_notifications = Notification.objects.filter(recipient=self.admin, title__icontains='reminder')
        self.assertGreater(owner_notifications.count(), 0)
        self.assertGreater(admin_notifications.count(), 0)

        first_count = Notification.objects.count()
        call_command('send_contract_reminders')
        second_count = Notification.objects.count()
        self.assertEqual(first_count, second_count)
