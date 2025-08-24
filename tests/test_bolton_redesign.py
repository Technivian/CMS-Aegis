
import os
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from contracts.models import Contract


class BoltonRedesignTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123',
            email='test@example.com'
        )
        self.client.login(username='testuser', password='testpass123')
        
        # Set feature flag
        os.environ['FEATURE_REDESIGN'] = 'true'

    def test_dashboard_stat_cards(self):
        """Test that dashboard displays stat cards when redesign is enabled"""
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        
        # Check for stat cards structure
        self.assertContains(response, 'grid grid-cols-4 gap-6')
        self.assertContains(response, 'Total Contracts')
        self.assertContains(response, 'Pending Tasks')
        self.assertContains(response, 'Active Workflows')
        self.assertContains(response, 'Expiring Soon')

    def test_dashboard_container_constraint(self):
        """Test that dashboard uses max-w-[1200px] container"""
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'max-w-[1200px] mx-auto px-6')

    def test_dashboard_top_bar(self):
        """Test that dashboard has proper top bar with search and new contract button"""
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        
        # Check for search input
        self.assertContains(response, 'Search contracts, workflows...')
        self.assertContains(response, '@keydown.slash.window.prevent')
        
        # Check for new contract button
        self.assertContains(response, 'New Contract')
        self.assertContains(response, 'bg-blue-600')

    def test_dashboard_saved_views(self):
        """Test that dashboard displays saved views chips"""
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        
        self.assertContains(response, 'Saved Views:')
        self.assertContains(response, 'Pending Review')
        self.assertContains(response, 'Active Contracts')

    def test_contracts_table_structure(self):
        """Test that contracts table has proper structure and sticky header"""
        # Create test contract
        Contract.objects.create(
            title='Test Contract',
            content='Test content',
            status='DRAFT',
            created_by=self.user
        )
        
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        
        # Check for sticky header
        self.assertContains(response, 'sticky top-16 z-20')
        
        # Check for all required columns
        self.assertContains(response, 'Name')
        self.assertContains(response, 'Stage')
        self.assertContains(response, 'Agreement Date')
        self.assertContains(response, 'Region')
        self.assertContains(response, 'Value')
        self.assertContains(response, 'Counterparty')
        self.assertContains(response, 'Owner')
        self.assertContains(response, 'Updated')

    def test_contract_row_click_functionality(self):
        """Test that contract rows have proper click handlers for drawer"""
        Contract.objects.create(
            title='Test Contract',
            content='Test content',
            status='DRAFT',
            created_by=self.user
        )
        
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        
        # Check for drawer functionality
        self.assertContains(response, 'openContractDrawer')
        self.assertContains(response, '@click="openContractDrawer')
        self.assertContains(response, '@keydown.enter="openContractDrawer')

    def test_contract_drawer_structure(self):
        """Test that contract drawer has proper structure and accessibility"""
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        
        # Check for drawer element
        self.assertContains(response, 'w-[480px]')
        self.assertContains(response, 'Contract Details')
        
        # Check for action buttons
        self.assertContains(response, 'Edit Contract')
        self.assertContains(response, 'Start/Advance Workflow')

    def test_contracts_list_url_sync_filters(self):
        """Test that contracts list supports URL-synced filters"""
        response = self.client.get(reverse('contracts:contract_list'))
        self.assertEqual(response.status_code, 200)
        
        # Check for filter controls
        self.assertContains(response, 'Status:')
        self.assertContains(response, 'Owner:')
        self.assertContains(response, 'Value Range:')
        
        # Check for filter update functionality
        self.assertContains(response, 'updateFilters()')
        self.assertContains(response, 'loadFiltersFromURL()')

    def test_accessibility_features(self):
        """Test that accessibility features are implemented"""
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        
        # Check for focus rings
        self.assertContains(response, 'focus:ring-2')
        self.assertContains(response, 'focus:ring-blue-500')
        
        # Check for ARIA labels
        self.assertContains(response, 'aria-label')
        
        # Check for tabindex for keyboard navigation
        self.assertContains(response, 'tabindex="0"')

    def test_typography_and_spacing(self):
        """Test that proper typography and spacing is used"""
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        
        # Check for Inter font and proper sizing
        self.assertContains(response, 'text-[32px] leading-[36px]')  # Page title
        self.assertContains(response, 'text-[24px] leading-[28px]')  # Section headers
        self.assertContains(response, 'text-[14px] leading-[16px]')  # Base text
        
        # Check for 8px spacing scale
        self.assertContains(response, 'space-y-6')
        self.assertContains(response, 'gap-6')

    def tearDown(self):
        """Clean up environment variables"""
        if 'FEATURE_REDESIGN' in os.environ:
            del os.environ['FEATURE_REDESIGN']
