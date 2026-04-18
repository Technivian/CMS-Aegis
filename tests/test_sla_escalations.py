from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from contracts.models import ApprovalRequest, Contract, Notification, Organization, OrganizationMembership, SignatureRequest


User = get_user_model()


class SLAEscalationTests(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(name='SLA Org', slug='sla-org')
        self.owner = User.objects.create_user(username='sla-owner', password='testpass123')
        self.assignee = User.objects.create_user(username='sla-assignee', password='testpass123')

        OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.owner,
            role=OrganizationMembership.Role.OWNER,
            is_active=True,
        )
        OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.assignee,
            role=OrganizationMembership.Role.ADMIN,
            is_active=True,
        )

        self.contract = Contract.objects.create(
            organization=self.organization,
            title='SLA Contract',
            contract_type=Contract.ContractType.NDA,
            status=Contract.Status.ACTIVE,
            counterparty='Acme',
            governing_law='Delaware',
            jurisdiction='New York',
            created_by=self.owner,
        )

    def test_overdue_approval_request_escalates_and_notifies(self):
        approval_request = ApprovalRequest.objects.create(
            organization=self.organization,
            contract=self.contract,
            approval_step='LEGAL_REVIEW',
            assigned_to=self.assignee,
            status=ApprovalRequest.Status.PENDING,
            due_date=timezone.now() - timedelta(days=1),
        )

        call_command('send_contract_reminders')

        approval_request.refresh_from_db()
        self.assertEqual(approval_request.status, ApprovalRequest.Status.ESCALATED)
        self.assertTrue(
            Notification.objects.filter(
                recipient=self.assignee,
                notification_type=Notification.NotificationType.APPROVAL,
                title__startswith='Approval overdue:',
            ).exists()
        )

    def test_stale_signature_request_expires_and_notifies(self):
        signature_request = SignatureRequest.objects.create(
            organization=self.organization,
            contract=self.contract,
            signer_name='External Signer',
            signer_email='signer@example.com',
            status=SignatureRequest.Status.SENT,
            sent_at=timezone.now() - timedelta(days=10),
            created_by=self.owner,
        )

        call_command('send_contract_reminders')

        signature_request.refresh_from_db()
        self.assertEqual(signature_request.status, SignatureRequest.Status.EXPIRED)
        self.assertTrue(
            Notification.objects.filter(
                recipient=self.owner,
                notification_type=Notification.NotificationType.APPROVAL,
                title__startswith='Signature overdue:',
            ).exists()
        )
