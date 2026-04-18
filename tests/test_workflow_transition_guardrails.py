from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from contracts.models import (
    ApprovalRequest,
    Contract,
    Organization,
    OrganizationMembership,
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
