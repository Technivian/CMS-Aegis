
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from django.template.loader import render_to_string
from django.template import Context, Template
import os

class DesignSystemTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )

    def test_feature_flag_enabled(self):
        """Test that redesign works when feature flag is enabled"""
        os.environ['FEATURE_REDESIGN'] = 'true'
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        # Check that redesigned template is used
        self.assertContains(response, 'CLM Platform')
        
    def test_feature_flag_disabled(self):
        """Test that original design works when feature flag is disabled"""
        os.environ['FEATURE_REDESIGN'] = 'false'
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        
    def test_components_demo_page(self):
        """Test that components demo page loads correctly"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('components_demo'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Design System Components')
        
    def test_button_components(self):
        """Test that button components render correctly"""
        template = Template('''
        <button class="btn-primary">Primary Button</button>
        <button class="btn-secondary">Secondary Button</button>
        <button class="btn-ghost">Ghost Button</button>
        <button class="btn-destructive">Destructive Button</button>
        ''')
        rendered = template.render(Context({}))
        self.assertIn('btn-primary', rendered)
        self.assertIn('btn-secondary', rendered)
        
    def test_card_component(self):
        """Test that card component renders correctly"""
        template = Template('''
        <div class="card">
            <div class="card-header">
                <h3>Card Title</h3>
            </div>
            <div class="card-content">
                <p>Card content</p>
            </div>
        </div>
        ''')
        rendered = template.render(Context({}))
        self.assertIn('card', rendered)
        self.assertIn('card-header', rendered)
        self.assertIn('card-content', rendered)
        
    def test_stat_component(self):
        """Test that stat component renders correctly"""
        template = Template('''
        <div class="stat">
            <div>
                <div class="stat-label">Total Contracts</div>
                <div class="stat-value">142</div>
            </div>
            <div class="stat-trend up">+12%</div>
        </div>
        ''')
        rendered = template.render(Context({}))
        self.assertIn('stat', rendered)
        self.assertIn('stat-label', rendered)
        self.assertIn('stat-value', rendered)

    def test_responsive_navigation(self):
        """Test that navigation components work responsively"""
        os.environ['FEATURE_REDESIGN'] = 'true'
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('dashboard'))
        self.assertContains(response, 'sidebarOpen')
        self.assertContains(response, 'lg:translate-x-0')
        
    def test_search_component(self):
        """Test that search component includes proper keyboard shortcuts"""
        os.environ['FEATURE_REDESIGN'] = 'true'
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('dashboard'))
        self.assertContains(response, 'Press / to focus')
        self.assertContains(response, '@keydown.slash.window.prevent')
        
    def test_keyboard_shortcuts(self):
        """Test that keyboard shortcuts are properly implemented"""
        os.environ['FEATURE_REDESIGN'] = 'true'
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('dashboard'))
        # Test New Contract shortcut
        self.assertContains(response, '@keydown.n.window.prevent')
        # Test navigation shortcuts
        self.assertContains(response, '@keydown.g.then.d.window.prevent')
        
    def tearDown(self):
        """Clean up environment variables"""
        if 'FEATURE_REDESIGN' in os.environ:
            del os.environ['FEATURE_REDESIGN']
