
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
import os

class RedesignLayoutTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        os.environ['FEATURE_REDESIGN'] = 'true'

    def test_base_redesign_template(self):
        """Test that base_redesign.html loads correctly"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        # Check for redesign elements
        self.assertContains(response, 'CLM Platform')
        self.assertContains(response, 'sidebarOpen')
        
    def test_sidebar_navigation_items(self):
        """Test that sidebar contains expected navigation items"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('dashboard'))
        # Check navigation sections
        self.assertContains(response, 'My Views')
        self.assertContains(response, 'Quick Actions')
        self.assertContains(response, 'Saved Filters')
        
        # Check navigation links
        self.assertContains(response, 'Dashboard')
        self.assertContains(response, 'All Contracts')
        self.assertContains(response, 'Tasks')
        self.assertContains(response, 'Workflows')
        
    def test_top_navigation_elements(self):
        """Test that top navigation contains expected elements"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('dashboard'))
        # Check for search
        self.assertContains(response, 'Search contracts, tasks, workflows')
        # Check for new contract button
        self.assertContains(response, 'New Contract')
        # Check for user menu
        self.assertContains(response, 'Profile')
        self.assertContains(response, 'Sign out')
        
    def test_mobile_responsive_elements(self):
        """Test that mobile responsive elements are present"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('dashboard'))
        # Check for mobile sidebar toggle
        self.assertContains(response, 'lg:hidden')
        # Check for responsive classes
        self.assertContains(response, 'sm:px-6')
        self.assertContains(response, 'lg:px-8')
        
    def test_accessibility_features(self):
        """Test that accessibility features are implemented"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('dashboard'))
        # Check for ARIA labels
        self.assertContains(response, 'aria-expanded')
        # Check for focus management
        self.assertContains(response, 'focus:outline-none')
        self.assertContains(response, 'focus:ring-2')
        
    def test_dashboard_stats_layout(self):
        """Test that dashboard stats are properly laid out"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('dashboard'))
        # Check for stats grid
        self.assertContains(response, 'lg:grid-cols-4')
        # Check for stat components
        self.assertContains(response, 'stat-label')
        self.assertContains(response, 'stat-value')
        
    def test_activity_feed_layout(self):
        """Test that activity feed is properly structured"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('dashboard'))
        # Check for activity section
        self.assertContains(response, 'Recent Activity')
        # Check for activity items structure
        self.assertContains(response, 'flex items-start gap-3')
        
    def test_quick_actions_section(self):
        """Test that quick actions are properly displayed"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('dashboard'))
        # Check for quick actions
        self.assertContains(response, 'Quick Actions')
        self.assertContains(response, 'grid grid-cols-2 md:grid-cols-4')
        
    def test_saved_filters_chips(self):
        """Test that saved filter chips are displayed"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('dashboard'))
        # Check for filter chips
        self.assertContains(response, 'filter-chips')
        self.assertContains(response, 'Pending Review')
        self.assertContains(response, 'Active Contracts')
        
    def tearDown(self):
        if 'FEATURE_REDESIGN' in os.environ:
            del os.environ['FEATURE_REDESIGN']
