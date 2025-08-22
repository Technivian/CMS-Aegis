
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from config.feature_flags import is_feature_redesign_enabled
import os

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
        # Clean up any existing env var
        if 'FEATURE_REDESIGN' in os.environ:
            del os.environ['FEATURE_REDESIGN']
            
        # Start with flag disabled
        self.assertFalse(is_feature_redesign_enabled())
        
        # Toggle the flag
        response = self.client.post(reverse('toggle_redesign'))
        self.assertEqual(response.status_code, 302)
        
        # Verify flag is now enabled
        self.assertTrue(is_feature_redesign_enabled())
    
    def test_dashboard_uses_correct_template(self):
        """Test that dashboard uses correct template based on feature flag"""
        # Test with flag disabled
        if 'FEATURE_REDESIGN' in os.environ:
            del os.environ['FEATURE_REDESIGN']
        response = self.client.get(reverse('dashboard'))
        self.assertContains(response, 'Main Navigation Tabs (Bolton Style)')
        
        # Test with flag enabled
        os.environ['FEATURE_REDESIGN'] = 'true'
        response = self.client.get(reverse('dashboard'))
        self.assertContains(response, 'Global search')
        self.assertContains(response, 'My Views')
    
    def test_sidebar_navigation_elements(self):
        """Test that sidebar contains required navigation elements"""
        os.environ['FEATURE_REDESIGN'] = 'true'
        response = self.client.get(reverse('dashboard'))
        
        # Check for sidebar elements
        self.assertContains(response, 'Bolton CLM')
        self.assertContains(response, 'My Views')
        self.assertContains(response, 'Dashboard')
        self.assertContains(response, 'All Contracts')
        self.assertContains(response, 'Legal Tasks')
        self.assertContains(response, 'Active Workflows')
        self.assertContains(response, 'Quick Actions')
        self.assertContains(response, 'New Contract')
    
    def test_keyboard_shortcuts_javascript(self):
        """Test that keyboard shortcuts JavaScript is included"""
        os.environ['FEATURE_REDESIGN'] = 'true'
        response = self.client.get(reverse('dashboard'))
        
        # Check for keyboard shortcut handling
        self.assertContains(response, "e.key === '/'")
        self.assertContains(response, "e.key === 'n'")
        self.assertContains(response, "e.key === 'g'")
    
    def test_responsive_mobile_toggle(self):
        """Test that mobile sidebar toggle is present"""
        os.environ['FEATURE_REDESIGN'] = 'true'
        response = self.client.get(reverse('dashboard'))
        
        self.assertContains(response, 'mobileSidebarToggle')
        self.assertContains(response, 'lg:hidden')
    
    def test_max_width_content_grid(self):
        """Test that content has max-width constraint"""
        os.environ['FEATURE_REDESIGN'] = 'true'
        response = self.client.get(reverse('dashboard'))
        
        self.assertContains(response, 'max-w-7xl')
    
    def tearDown(self):
        # Clean up environment variable
        if 'FEATURE_REDESIGN' in os.environ:
            del os.environ['FEATURE_REDESIGN']
