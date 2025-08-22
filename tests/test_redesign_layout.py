
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from config.feature_flags import set_feature_flag, is_feature_enabled

class RedesignLayoutTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.client.login(username='testuser', password='testpass123')
    
    def test_feature_flag_toggle(self):
        """Test that feature flag can be toggled"""
        # Start with flag disabled
        set_feature_flag('FEATURE_REDESIGN', False)
        self.assertFalse(is_feature_enabled('FEATURE_REDESIGN'))
        
        # Toggle the flag
        response = self.client.post(reverse('toggle_redesign'))
        self.assertEqual(response.status_code, 302)
        
        # Verify flag is now enabled
        self.assertTrue(is_feature_enabled('FEATURE_REDESIGN'))
    
    def test_dashboard_uses_correct_template(self):
        """Test that dashboard uses correct template based on feature flag"""
        # Test with flag disabled
        set_feature_flag('FEATURE_REDESIGN', False)
        response = self.client.get(reverse('dashboard'))
        self.assertContains(response, 'Main Navigation Tabs (Bolton Style)')
        
        # Test with flag enabled
        set_feature_flag('FEATURE_REDESIGN', True)
        response = self.client.get(reverse('dashboard'))
        self.assertContains(response, 'Global Search')
        self.assertContains(response, 'My Views')
    
    def test_sidebar_navigation_elements(self):
        """Test that sidebar contains required navigation elements"""
        set_feature_flag('FEATURE_REDESIGN', True)
        response = self.client.get(reverse('dashboard'))
        
        # Check for sidebar sections
        self.assertContains(response, 'My Views')
        self.assertContains(response, 'Quick Actions')
        self.assertContains(response, 'Filters')
        
        # Check for navigation items
        self.assertContains(response, 'Dashboard')
        self.assertContains(response, 'All Contracts')
        self.assertContains(response, 'Legal Tasks')
        self.assertContains(response, 'Active Workflows')
    
    def test_keyboard_shortcuts_present(self):
        """Test that keyboard shortcut indicators are present"""
        set_feature_flag('FEATURE_REDESIGN', True)
        response = self.client.get(reverse('dashboard'))
        
        # Check for shortcut indicators
        self.assertContains(response, 'G D')  # Dashboard
        self.assertContains(response, 'G C')  # Contracts
        self.assertContains(response, 'G T')  # Tasks
        self.assertContains(response, 'G W')  # Workflows
        self.assertContains(response, 'N')    # New Contract
    
    def test_global_search_present(self):
        """Test that global search is present in redesigned layout"""
        set_feature_flag('FEATURE_REDESIGN', True)
        response = self.client.get(reverse('dashboard'))
        
        self.assertContains(response, 'global-search')
        self.assertContains(response, 'Search contracts, tasks, workflows...')
