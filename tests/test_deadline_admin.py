import datetime

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from contracts.models import Contract, Deadline, Organization, OrganizationMembership


User = get_user_model()


class DeadlineAdminTests(TestCase):
    def setUp(self):
        self.superuser = User.objects.create_superuser(
            username='admin',
            email='admin@example.com',
            password='testpass123',
        )
        self.organization = Organization.objects.create(name='Deadline Org', slug='deadline-org')
        self.owner = User.objects.create_user(username='owner', password='testpass123')
        OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.owner,
            role=OrganizationMembership.Role.OWNER,
            is_active=True,
        )
        self.contract = Contract.objects.create(
            organization=self.organization,
            title='Deadline Contract',
            contract_type='NDA',
            status='ACTIVE',
            created_by=self.owner,
        )
        self.overdue_deadline = Deadline.objects.create(
            title='Overdue Deadline',
            due_date=datetime.date.today() - datetime.timedelta(days=2),
            contract=self.contract,
            created_by=self.owner,
        )
        self.upcoming_deadline = Deadline.objects.create(
            title='Upcoming Deadline',
            due_date=datetime.date.today() + datetime.timedelta(days=5),
            contract=self.contract,
            created_by=self.owner,
        )

    def test_deadline_admin_changelist_shows_health_filter(self):
        self.client.force_login(self.superuser)
        response = self.client.get(reverse('admin:contracts_deadline_changelist'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-filter-title="deadline health"')
        self.assertContains(response, 'Overdue')

    def test_deadline_admin_overdue_filter_is_selective(self):
        self.client.force_login(self.superuser)
        response = self.client.get(
            reverse('admin:contracts_deadline_changelist'),
            {'deadline_health': 'overdue'},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.overdue_deadline.title)
        self.assertNotContains(response, self.upcoming_deadline.title)
