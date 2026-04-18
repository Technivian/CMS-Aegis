from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from contracts.models import Contract, Organization, OrganizationMembership


User = get_user_model()


class RepositorySavedViewsTests(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(name='Repo Org', slug='repo-org')
        self.user = User.objects.create_user(username='repo-user', password='testpass123')
        OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.user,
            role=OrganizationMembership.Role.OWNER,
            is_active=True,
        )
        Contract.objects.create(
            organization=self.organization,
            title='Repository Contract',
            contract_type=Contract.ContractType.NDA,
            status=Contract.Status.ACTIVE,
            counterparty='Acme',
            governing_law='Delaware',
            jurisdiction='New York',
            created_by=self.user,
        )

    def test_repository_page_renders_saved_view_controls(self):
        self.client.login(username='repo-user', password='testpass123')

        response = self.client.get(reverse('contracts:repository'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="saved-views"', html=False)
        self.assertContains(response, 'id="filter-chips"', html=False)
