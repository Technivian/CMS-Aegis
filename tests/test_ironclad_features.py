
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from contracts.models import Contract, LegalTask, Workflow
import os

class IroncladFeaturesTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        os.environ['FEATURE_REDESIGN'] = 'true'
        
        # Create test data
        self.contract = Contract.objects.create(
            title='Test Contract',
            content='Test content',
            status='ACTIVE',
            created_by=self.user
        )

    def test_contracts_table_advanced_features(self):
        """Test that contracts table has advanced features"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('contracts:contract_list'))
        self.assertEqual(response.status_code, 200)
        
        # Check for table features
        self.assertContains(response, 'contractsTable()')
        self.assertContains(response, 'sortField')
        self.assertContains(response, 'filteredContracts')
        
    def test_search_functionality(self):
        """Test that search functionality is implemented"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('contracts:contract_list'))
        # Check for search input
        self.assertContains(response, 'searchTerm')
        self.assertContains(response, 'debounceSearch()')
        
    def test_filter_functionality(self):
        """Test that filter functionality is comprehensive"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('contracts:contract_list'))
        # Check for filter options
        self.assertContains(response, 'showFilters')
        self.assertContains(response, 'filters.status')
        self.assertContains(response, 'filters.owner')
        self.assertContains(response, 'filters.dateRange')
        self.assertContains(response, 'filters.valueRange')
        
    def test_bulk_operations(self):
        """Test that bulk operations are available"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('contracts:contract_list'))
        # Check for bulk operations
        self.assertContains(response, 'selectedRows')
        self.assertContains(response, 'bulkTag()')
        self.assertContains(response, 'bulkAssign()')
        self.assertContains(response, 'bulkArchive()')
        
    def test_preview_drawer(self):
        """Test that preview drawer is implemented"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('contracts:contract_list'))
        # Check for preview drawer
        self.assertContains(response, 'previewOpen')
        self.assertContains(response, 'selectedContract')
        self.assertContains(response, 'openPreview(')
        
    def test_sortable_columns(self):
        """Test that columns are sortable"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('contracts:contract_list'))
        # Check for sort functionality
        self.assertContains(response, 'sort(\'title\')')
        self.assertContains(response, 'sort(\'status\')')
        self.assertContains(response, 'sortDirection')
        
    def test_filter_chips(self):
        """Test that filter chips are displayed"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('contracts:contract_list'))
        # Check for filter chips
        self.assertContains(response, 'activeFilters')
        self.assertContains(response, 'removeFilter(')
        
    def test_virtualization_support(self):
        """Test that table supports large datasets"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('contracts:contract_list'))
        # Check for virtualization patterns
        self.assertContains(response, 'filteredContracts')
        self.assertContains(response, 'x-for="contract in filteredContracts"')
        
    def test_empty_state_handling(self):
        """Test that empty states are handled properly"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('contracts:contract_list'))
        # Check for empty state
        self.assertContains(response, 'filteredContracts.length === 0')
        self.assertContains(response, 'empty-state')
        
    def test_workflow_stepper(self):
        """Test that workflow stepper is displayed in preview"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('contracts:contract_list'))
        # Check for stepper
        self.assertContains(response, 'stepper')
        self.assertContains(response, 'step completed')
        self.assertContains(response, 'step active')
        
    def tearDown(self):
        if 'FEATURE_REDESIGN' in os.environ:
            del os.environ['FEATURE_REDESIGN']
