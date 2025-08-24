
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from contracts.models import Contract, LegalTask, Workflow
import os

class RedesignComponentsTestCase(TestCase):
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

    def test_dashboard_redesign_loads(self):
        """Test dashboard loads with redesign components"""
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Total Contracts')
        self.assertContains(response, 'Pending Tasks')
        self.assertContains(response, 'Active Workflows')
        self.assertContains(response, 'Expiring Soon')

    def test_contracts_list_redesign(self):
        """Test contracts list with redesign components"""
        # Create test contract
        Contract.objects.create(
            title='Test Contract',
            content='Test content',
            status=Contract.Status.DRAFT
        )
        
        response = self.client.get(reverse('contracts:contract_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Test Contract')
        self.assertContains(response, 'New Contract')
        self.assertContains(response, 'Search contracts')

    def test_component_demo_page(self):
        """Test component demo page loads all components"""
        response = self.client.get(reverse('components_demo'))
        self.assertEqual(response.status_code, 200)
        
        # Check for key component sections
        self.assertContains(response, 'Typography')
        self.assertContains(response, 'Color Tokens')
        self.assertContains(response, 'Buttons')
        self.assertContains(response, 'Cards & Stats')
        self.assertContains(response, 'Form Controls')
        self.assertContains(response, 'Tables')

    def test_navigation_structure(self):
        """Test navigation components are present"""
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        
        # Check for navigation elements
        self.assertContains(response, 'CLM Pro')
        self.assertContains(response, 'Dashboard')
        self.assertContains(response, 'Contracts')
        self.assertContains(response, 'Tasks')
        self.assertContains(response, 'Repository')
        self.assertContains(response, 'Workflows')

    def test_accessibility_features(self):
        """Test accessibility features are implemented"""
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        
        # Check for accessibility attributes
        self.assertContains(response, 'accesskey')
        self.assertContains(response, 'aria-')
        self.assertContains(response, 'focus:')

    def test_responsive_design_classes(self):
        """Test responsive design classes are present"""
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        
        # Check for responsive classes
        self.assertContains(response, 'md:')
        self.assertContains(response, 'lg:')
        self.assertContains(response, 'sm:')

    def test_feature_flag_toggle(self):
        """Test feature flag toggle functionality"""
        # Test with feature flag on
        os.environ['FEATURE_REDESIGN'] = 'true'
        response = self.client.get(reverse('dashboard'))
        self.assertContains(response, 'Feature Redesign ON')
        
        # Test with feature flag off
        os.environ['FEATURE_REDESIGN'] = 'false'
        response = self.client.get(reverse('dashboard'))
        self.assertContains(response, 'Feature Redesign OFF')

    def tearDown(self):
        # Clean up environment
        if 'FEATURE_REDESIGN' in os.environ:
            del os.environ['FEATURE_REDESIGN']
