from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from contracts.models import (
    ApprovalRequest,
    Contract,
    Notification,
    Organization,
    OrganizationMembership,
    Workflow,
    WorkflowStep,
    SignatureRequest,
)


User = get_user_model()


class WorkflowTransitionGuardrailsTests(TestCase):
    def setUp(self):
        self.client = Client()

        self.owner = User.objects.create_user(
            username='owner-user',
            email='owner@example.com',
            password='testpass123',
        )
        self.assigned = User.objects.create_user(
            username='assigned-user',
            email='assigned@example.com',
            password='testpass123',
        )
        self.member = User.objects.create_user(
            username='member-user',
            email='member@example.com',
            password='testpass123',
        )

        self.org = Organization.objects.create(name='Transitions Org', slug='transitions-org')
        OrganizationMembership.objects.create(
            organization=self.org,
            user=self.owner,
            role=OrganizationMembership.Role.OWNER,
            is_active=True,
        )
        OrganizationMembership.objects.create(
            organization=self.org,
            user=self.assigned,
            role=OrganizationMembership.Role.ADMIN,
            is_active=True,
        )
        OrganizationMembership.objects.create(
            organization=self.org,
            user=self.member,
            role=OrganizationMembership.Role.MEMBER,
            is_active=True,
        )

        self.contract = Contract.objects.create(
            organization=self.org,
            title='Transition Test Contract',
            content='Contract for transition hardening tests',
            status=Contract.Status.ACTIVE,
            created_by=self.owner,
        )

        self.signature_request = SignatureRequest.objects.create(
            organization=self.org,
            contract=self.contract,
            signer_name='Signer Person',
            signer_email='signer@example.com',
            signer_role='CEO',
            status=SignatureRequest.Status.PENDING,
            order=1,
            created_by=self.owner,
        )

        self.approval_request = ApprovalRequest.objects.create(
            organization=self.org,
            contract=self.contract,
            approval_step='Legal Review',
            status=ApprovalRequest.Status.PENDING,
            assigned_to=self.assigned,
        )
        self.workflow = Workflow.objects.create(
            organization=self.org,
            title='Transition Workflow',
            description='Workflow for transition hardening tests',
            contract=self.contract,
            created_by=self.owner,
        )

    def _signature_update_payload(self, status):
        return {
            'contract': self.contract.id,
            'document': '',
            'signer_name': self.signature_request.signer_name,
            'signer_email': self.signature_request.signer_email,
            'signer_role': self.signature_request.signer_role,
            'status': status,
            'order': self.signature_request.order,
        }

    def _approval_update_payload(self, status):
        return {
            'contract': self.contract.id,
            'approval_step': self.approval_request.approval_step,
            'status': status,
            'assigned_to': self.assigned.id,
            'comments': 'Transition update',
            'due_date': '',
        }

    def test_signature_request_rejects_invalid_status_transition(self):
        self.assertTrue(self.client.login(username='owner-user', password='testpass123'))
        response = self.client.post(
            reverse('contracts:signature_request_update', args=[self.signature_request.id]),
            data=self._signature_update_payload(SignatureRequest.Status.SIGNED),
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Invalid signature status transition.')

        self.signature_request.refresh_from_db()
        self.assertEqual(self.signature_request.status, SignatureRequest.Status.PENDING)

    def test_signature_request_blocks_unauthorized_member_transition(self):
        self.assertTrue(self.client.login(username='member-user', password='testpass123'))
        response = self.client.post(
            reverse('contracts:signature_request_update', args=[self.signature_request.id]),
            data=self._signature_update_payload(SignatureRequest.Status.SENT),
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'You are not authorized to perform this signature transition.')

        self.signature_request.refresh_from_db()
        self.assertEqual(self.signature_request.status, SignatureRequest.Status.PENDING)

    def test_signature_request_routing_blocks_later_signer_until_previous_request_completes(self):
        signer = User.objects.create_user(
            username='signer-user',
            email='signer@example.com',
            password='testpass123',
        )
        OrganizationMembership.objects.create(
            organization=self.org,
            user=signer,
            role=OrganizationMembership.Role.MEMBER,
            is_active=True,
        )

        routing_contract = Contract.objects.create(
            organization=self.org,
            title='Routing Contract',
            content='Contract for signature routing tests',
            status=Contract.Status.ACTIVE,
            created_by=self.owner,
        )
        earlier_request = SignatureRequest.objects.create(
            organization=self.org,
            contract=routing_contract,
            signer_name='Primary Signer',
            signer_email='signer@example.com',
            signer_role='CFO',
            status=SignatureRequest.Status.SENT,
            order=1,
            created_by=self.owner,
            sent_at=timezone.now(),
        )
        later_request = SignatureRequest.objects.create(
            organization=self.org,
            contract=routing_contract,
            signer_name='Secondary Signer',
            signer_email='signer@example.com',
            signer_role='CEO',
            status=SignatureRequest.Status.SENT,
            order=2,
            created_by=self.owner,
            sent_at=timezone.now(),
        )

        self.assertFalse(later_request.is_routing_ready())

        self.assertTrue(self.client.login(username='signer-user', password='testpass123'))
        response = self.client.get(reverse('contracts:signature_request_detail', args=[later_request.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Routing is waiting on one earlier signer step')
        self.assertContains(response, 'No next actions are currently available for your role.')

        post_response = self.client.post(
            reverse('contracts:signature_request_transition', args=[later_request.id, SignatureRequest.Status.VIEWED]),
        )
        self.assertEqual(post_response.status_code, 403)

        earlier_request.status = SignatureRequest.Status.SIGNED
        earlier_request.signed_at = timezone.now()
        earlier_request.save(update_fields=['status', 'signed_at'])
        later_request.refresh_from_db()
        self.assertTrue(later_request.is_routing_ready())

    def test_signature_request_detail_surfaces_actions_and_updates_status(self):
        self.assertTrue(self.client.login(username='owner-user', password='testpass123'))
        response = self.client.get(reverse('contracts:signature_request_detail', args=[self.signature_request.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Quick Actions')
        self.assertContains(response, 'Mark as Sent')
        self.assertContains(response, 'Lifecycle Timeline')

        post_response = self.client.post(
            reverse('contracts:signature_request_transition', args=[self.signature_request.id, SignatureRequest.Status.SENT]),
        )
        self.assertEqual(post_response.status_code, 302)
        self.assertRedirects(
            post_response,
            reverse('contracts:signature_request_detail', args=[self.signature_request.id]),
            fetch_redirect_response=False,
        )

        self.signature_request.refresh_from_db()
        self.assertEqual(self.signature_request.status, SignatureRequest.Status.SENT)
        self.assertIsNotNone(self.signature_request.sent_at)

    def test_signature_request_send_reminder_creates_notifications_once(self):
        self.signature_request.status = SignatureRequest.Status.SENT
        self.signature_request.sent_at = timezone.now() - timedelta(days=8)
        self.signature_request.save(update_fields=['status', 'sent_at'])

        self.assertTrue(self.client.login(username='owner-user', password='testpass123'))
        response = self.client.post(reverse('contracts:signature_request_send_reminder', args=[self.signature_request.id]))
        self.assertEqual(response.status_code, 302)

        reminder_link = reverse('contracts:signature_request_detail', args=[self.signature_request.id])
        self.assertEqual(
            Notification.objects.filter(
                title__icontains='Signature reminder:',
                link=reminder_link,
                notification_type=Notification.NotificationType.SYSTEM,
            ).count(),
            2,
        )

        second_response = self.client.post(reverse('contracts:signature_request_send_reminder', args=[self.signature_request.id]))
        self.assertEqual(second_response.status_code, 302)
        self.assertEqual(
            Notification.objects.filter(
                title__icontains='Signature reminder:',
                link=reminder_link,
                notification_type=Notification.NotificationType.SYSTEM,
            ).count(),
            2,
        )

    def test_signature_request_transition_blocks_unauthorized_member(self):
        self.assertTrue(self.client.login(username='member-user', password='testpass123'))
        response = self.client.post(
            reverse('contracts:signature_request_transition', args=[self.signature_request.id, SignatureRequest.Status.SENT]),
        )
        self.assertEqual(response.status_code, 403)

        self.signature_request.refresh_from_db()
        self.assertEqual(self.signature_request.status, SignatureRequest.Status.PENDING)

    def test_approval_request_blocks_unauthorized_member_transition(self):
        self.assertTrue(self.client.login(username='member-user', password='testpass123'))
        response = self.client.post(
            reverse('contracts:approval_request_update', args=[self.approval_request.id]),
            data=self._approval_update_payload(ApprovalRequest.Status.APPROVED),
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'You are not authorized to perform this approval transition.')

        self.approval_request.refresh_from_db()
        self.assertEqual(self.approval_request.status, ApprovalRequest.Status.PENDING)

    def test_approval_request_rejects_terminal_transition(self):
        self.approval_request.status = ApprovalRequest.Status.APPROVED
        self.approval_request.save(update_fields=['status'])

        self.assertTrue(self.client.login(username='owner-user', password='testpass123'))
        response = self.client.post(
            reverse('contracts:approval_request_update', args=[self.approval_request.id]),
            data=self._approval_update_payload(ApprovalRequest.Status.REJECTED),
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Invalid approval status transition.')

        self.approval_request.refresh_from_db()
        self.assertEqual(self.approval_request.status, ApprovalRequest.Status.APPROVED)

    def test_assigned_approver_can_approve_and_decision_metadata_is_recorded(self):
        self.assertTrue(self.client.login(username='assigned-user', password='testpass123'))
        response = self.client.post(
            reverse('contracts:approval_request_update', args=[self.approval_request.id]),
            data=self._approval_update_payload(ApprovalRequest.Status.APPROVED),
        )
        self.assertEqual(response.status_code, 302)

        self.approval_request.refresh_from_db()
        self.assertEqual(self.approval_request.status, ApprovalRequest.Status.APPROVED)
        self.assertEqual(self.approval_request.decided_by_id, self.assigned.id)
        self.assertIsNotNone(self.approval_request.decided_at)

    def test_workflow_detail_surfaces_add_step_form_and_creates_step(self):
        self.assertTrue(self.client.login(username='owner-user', password='testpass123'))
        response = self.client.get(reverse('contracts:workflow_detail', args=[self.workflow.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Add Workflow Step')
        self.assertContains(response, 'Workflow Steps')

        post_response = self.client.post(
            reverse('contracts:workflow_step_add', args=[self.workflow.id]),
            data={
                'name': 'Legal Review',
                'description': 'Review the draft contract',
                'status': WorkflowStep.Status.PENDING,
                'assigned_to': self.assigned.id,
                'order': 1,
                'due_date': '',
            },
        )
        self.assertEqual(post_response.status_code, 302)
        self.assertRedirects(
            post_response,
            reverse('contracts:workflow_detail', args=[self.workflow.id]),
            fetch_redirect_response=False,
        )

        step = WorkflowStep.objects.get(workflow=self.workflow, name='Legal Review')
        self.assertEqual(step.description, 'Review the draft contract')
        self.assertEqual(step.assigned_to_id, self.assigned.id)

        editor_response = self.client.get(reverse('contracts:workflow_step_update', args=[step.id]))
        self.assertEqual(editor_response.status_code, 200)
        self.assertContains(editor_response, 'Update Workflow Step')
