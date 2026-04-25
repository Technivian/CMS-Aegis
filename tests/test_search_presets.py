from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from contracts.models import Contract, Organization, OrganizationMembership, SearchPreset


User = get_user_model()


class SearchPresetTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='search-owner', password='pass12345')
        self.organization = Organization.objects.create(name='Search Org', slug='search-org')
        OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.user,
            role=OrganizationMembership.Role.OWNER,
            is_active=True,
        )
        Contract.objects.create(
            organization=self.organization,
            title='Acme Master Services Agreement',
            status=Contract.Status.ACTIVE,
            created_by=self.user,
        )
        self.client.login(username='search-owner', password='pass12345')

    def test_save_load_and_delete_search_preset(self):
        response = self.client.post(
            reverse('contracts:save_search_preset'),
            data={
                'name': 'Acme Search',
                'q': 'Acme',
                'type': '',
                'status': 'ACTIVE',
                'jurisdiction': '',
                'search_mode': 'keyword',
            },
        )
        self.assertEqual(response.status_code, 302)
        preset = SearchPreset.objects.get(organization=self.organization, created_by=self.user, name='Acme Search')

        loaded = self.client.get(reverse('contracts:global_search'), {'preset_id': preset.id})
        self.assertEqual(loaded.status_code, 200)
        self.assertEqual(loaded.context['q'], 'Acme')
        self.assertContains(loaded, 'Acme Search')
        self.assertContains(loaded, 'Acme Master Services Agreement')

        delete_response = self.client.post(reverse('contracts:delete_search_preset', args=[preset.id]))
        self.assertEqual(delete_response.status_code, 302)
        self.assertFalse(SearchPreset.objects.filter(pk=preset.id).exists())
