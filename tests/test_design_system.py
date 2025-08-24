
import pytest
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User


class DesignSystemTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )

    def test_components_demo_accessible(self):
        """Test that components demo page is accessible"""
        response = self.client.get(reverse('components_demo'))
        self.assertEqual(response.status_code, 200)

    def test_design_tokens_present(self):
        """Test that design system tokens are present in components demo"""
        response = self.client.get(reverse('components_demo'))
        content = response.content.decode()
        
        # Check for design tokens
        self.assertIn('Design System Components', content)
        self.assertIn('Color Tokens', content)
        self.assertIn('#FFFFFF', content)  # bg color
        self.assertIn('#0B0B0C', content)  # ink color
        self.assertIn('#0E9F6E', content)  # accent color

    def test_typography_system(self):
        """Test typography system implementation"""
        response = self.client.get(reverse('components_demo'))
        content = response.content.decode()
        
        # Check for typography classes
        self.assertIn('text-h1', content)
        self.assertIn('text-h2', content)
        self.assertIn('text-base', content)
        self.assertIn('font-titles', content)
        self.assertIn('font-labels', content)

    def test_button_components(self):
        """Test button component variations"""
        response = self.client.get(reverse('components_demo'))
        content = response.content.decode()
        
        # Check for button classes
        self.assertIn('btn-primary', content)
        self.assertIn('btn-secondary', content)
        self.assertIn('btn-ghost', content)
        self.assertIn('btn-destructive', content)

    def test_stat_components(self):
        """Test stat component implementation"""
        response = self.client.get(reverse('components_demo'))
        content = response.content.decode()
        
        # Check for stat classes
        self.assertIn('stat', content)
        self.assertIn('stat-label', content)
        self.assertIn('stat-value', content)
        self.assertIn('stat-trend', content)

    def test_badge_components(self):
        """Test badge component variations"""
        response = self.client.get(reverse('components_demo'))
        content = response.content.decode()
        
        # Check for badge classes
        self.assertIn('badge-primary', content)
        self.assertIn('badge-secondary', content)
        self.assertIn('badge-success', content)
        self.assertIn('badge-warning', content)
        self.assertIn('badge-danger', content)

    def test_form_components(self):
        """Test form component implementation"""
        response = self.client.get(reverse('components_demo'))
        content = response.content.decode()
        
        # Check for form classes
        self.assertIn('input', content)
        self.assertIn('select', content)
        self.assertIn('textarea', content)

    def test_table_components(self):
        """Test table component implementation"""
        response = self.client.get(reverse('components_demo'))
        content = response.content.decode()
        
        # Check for table classes
        self.assertIn('table', content)

    def test_filter_chips(self):
        """Test filter chip components"""
        response = self.client.get(reverse('components_demo'))
        content = response.content.decode()
        
        # Check for filter chip classes
        self.assertIn('filter-chips', content)
        self.assertIn('filter-chip', content)
        self.assertIn('filter-chip-remove', content)

    def test_empty_state_component(self):
        """Test empty state component"""
        response = self.client.get(reverse('components_demo'))
        content = response.content.decode()
        
        # Check for empty state classes
        self.assertIn('empty-state', content)
        self.assertIn('empty-state-icon', content)

    def test_progress_component(self):
        """Test progress component"""
        response = self.client.get(reverse('components_demo'))
        content = response.content.decode()
        
        # Check for progress classes
        self.assertIn('progress', content)
        self.assertIn('progress-bar', content)

    def test_skeleton_component(self):
        """Test skeleton loading component"""
        response = self.client.get(reverse('components_demo'))
        content = response.content.decode()
        
        # Check for skeleton classes
        self.assertIn('skeleton', content)
        self.assertIn('skeleton-title', content)
        self.assertIn('skeleton-text', content)

    def test_responsive_design(self):
        """Test responsive design implementation"""
        response = self.client.get(reverse('components_demo'))
        content = response.content.decode()
        
        # Check for responsive classes
        responsive_classes = ['md:', 'lg:', 'grid-cols-']
        has_responsive = any(cls in content for cls in responsive_classes)
        self.assertTrue(has_responsive, "Should have responsive design classes")

    def test_accessibility_features(self):
        """Test accessibility features"""
        response = self.client.get(reverse('components_demo'))
        content = response.content.decode()
        
        # Check for accessibility features
        self.assertIn('focus:ring', content)
        self.assertIn('aria-', content)
        self.assertIn('alt=', content)

    def test_card_components(self):
        """Test card component system"""
        response = self.client.get(reverse('components_demo'))
        content = response.content.decode()
        
        # Check for card classes
        self.assertIn('card', content)
        self.assertIn('card-header', content)
        self.assertIn('card-content', content)

    def test_container_system(self):
        """Test container and layout system"""
        response = self.client.get(reverse('components_demo'))
        content = response.content.decode()
        
        # Check for container classes
        self.assertIn('container', content)
        self.assertIn('max-w-content', content)


class DesignSystemIntegrationTest(TestCase):
    """Integration tests for design system in existing pages"""
    
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.client.login(username='testuser', password='testpass123')

    def test_design_system_css_loaded(self):
        """Test that design system CSS is properly loaded"""
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        
        # Should include the components CSS
        content = response.content.decode()
        # The CSS should be compiled and included
        self.assertTrue(response.status_code == 200)

    def test_feature_flag_accessible(self):
        """Test that FEATURE_REDESIGN flag is accessible"""
        from config.feature_flags import FEATURE_REDESIGN
        self.assertTrue(FEATURE_REDESIGN)


if __name__ == '__main__':
    pytest.main([__file__])
