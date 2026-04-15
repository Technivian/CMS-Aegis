import os

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from contracts.models import (
    CaseAssessment,
    CaseIntakeProcess,
    Client as CareProvider,
    Organization,
    OrganizationMembership,
    ProviderProfile,
    RegionalConfiguration,
)
from contracts.views import _build_matching_suggestions_for_intake


class MatchingRecommendationsTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='match_user',
            email='match@example.com',
            password='testpass123',
        )
        self.organization = Organization.objects.create(name='Care Team Matching', slug='care-team-matching')
        OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.user,
            role=OrganizationMembership.Role.OWNER,
            is_active=True,
        )
        self.client.login(username='match_user', password='testpass123')
        os.environ['FEATURE_REDESIGN'] = 'true'

    def tearDown(self):
        if 'FEATURE_REDESIGN' in os.environ:
            del os.environ['FEATURE_REDESIGN']

    def test_matching_panel_shows_score_wait_capacity_reason(self):
        provider = CareProvider.objects.create(
            organization=self.organization,
            name='Aanbieder Noord',
            status=CareProvider.Status.ACTIVE,
            created_by=self.user,
        )
        ProviderProfile.objects.create(
            client=provider,
            offers_outpatient=True,
            handles_medium_urgency=True,
            current_capacity=1,
            max_capacity=4,
            average_wait_days=12,
        )

        intake = CaseIntakeProcess.objects.create(
            organization=self.organization,
            title='Intake Matching Test',
            status=CaseIntakeProcess.ProcessStatus.ASSESSMENT,
            urgency=CaseIntakeProcess.Urgency.MEDIUM,
            preferred_care_form=CaseIntakeProcess.CareForm.OUTPATIENT,
            start_date='2026-04-10',
            target_completion_date='2026-04-20',
            case_coordinator=self.user,
        )
        CaseAssessment.objects.create(
            intake=intake,
            assessment_status=CaseAssessment.AssessmentStatus.APPROVED_FOR_MATCHING,
            matching_ready=True,
            assessed_by=self.user,
        )

        response = self.client.get(reverse('careon:matching_dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Matchscore')
        self.assertContains(response, 'Wachttijd')
        self.assertContains(response, 'Capaciteit')
        self.assertContains(response, 'Matching')
        self.assertContains(response, 'Open casus voor toewijzing')

    def test_matching_panel_shows_region_match_badge(self):
        region = RegionalConfiguration.objects.create(
            organization=self.organization,
            region_name='ROAZ Noord',
            region_code='ROAZ001',
            region_type='ROAZ',
            status=RegionalConfiguration.Status.ACTIVE,
        )

        provider = CareProvider.objects.create(
            organization=self.organization,
            name='Aanbieder Regio',
            status=CareProvider.Status.ACTIVE,
            created_by=self.user,
        )
        profile = ProviderProfile.objects.create(
            client=provider,
            offers_outpatient=True,
            handles_medium_urgency=True,
            current_capacity=0,
            max_capacity=3,
            average_wait_days=10,
        )
        profile.served_regions.add(region)

        intake = CaseIntakeProcess.objects.create(
            organization=self.organization,
            title='Intake Region Match',
            status=CaseIntakeProcess.ProcessStatus.ASSESSMENT,
            urgency=CaseIntakeProcess.Urgency.MEDIUM,
            preferred_care_form=CaseIntakeProcess.CareForm.OUTPATIENT,
            preferred_region_type='ROAZ',
            preferred_region=region,
            start_date='2026-04-10',
            target_completion_date='2026-04-20',
            case_coordinator=self.user,
        )
        CaseAssessment.objects.create(
            intake=intake,
            assessment_status=CaseAssessment.AssessmentStatus.APPROVED_FOR_MATCHING,
            matching_ready=True,
            assessed_by=self.user,
        )

        response = self.client.get(reverse('careon:matching_dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Regio: match')


class MatchingExplainabilityUnitTests(TestCase):
    """Unit tests for the structured explanation data returned by the matching helper."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='explain_user',
            email='explain@example.com',
            password='testpass123',
        )
        self.organization = Organization.objects.create(name='Explain Org', slug='explain-org')

    def _make_intake(self, **kwargs):
        defaults = dict(
            organization=self.organization,
            title='Test Intake',
            status=CaseIntakeProcess.ProcessStatus.ASSESSMENT,
            urgency=CaseIntakeProcess.Urgency.MEDIUM,
            preferred_care_form=CaseIntakeProcess.CareForm.OUTPATIENT,
            start_date='2026-04-10',
            target_completion_date='2026-04-20',
            case_coordinator=self.user,
        )
        defaults.update(kwargs)
        return CaseIntakeProcess.objects.create(**defaults)

    def _make_profile(self, **kwargs):
        provider = CareProvider.objects.create(
            organization=self.organization,
            name=kwargs.pop('name', 'Test Aanbieder'),
            status=CareProvider.Status.ACTIVE,
            created_by=self.user,
        )
        defaults = dict(
            client=provider,
            offers_outpatient=True,
            handles_medium_urgency=True,
            current_capacity=2,
            max_capacity=5,
            average_wait_days=10,
        )
        defaults.update(kwargs)
        return ProviderProfile.objects.create(**defaults)

    def test_suggestion_contains_explanation_key(self):
        intake = self._make_intake()
        profile = self._make_profile()
        profiles = ProviderProfile.objects.filter(pk=profile.pk).select_related('client').prefetch_related('target_care_categories')

        results = _build_matching_suggestions_for_intake(intake, profiles)

        self.assertGreater(len(results), 0)
        self.assertIn('explanation', results[0])

    def test_explanation_has_required_keys(self):
        intake = self._make_intake()
        profile = self._make_profile()
        profiles = ProviderProfile.objects.filter(pk=profile.pk).select_related('client').prefetch_related('target_care_categories')

        results = _build_matching_suggestions_for_intake(intake, profiles)
        explanation = results[0]['explanation']

        for key in ('fit_summary', 'factors', 'confidence', 'confidence_reason', 'trade_offs', 'verify_manually'):
            self.assertIn(key, explanation, f"Missing key: {key}")

    def test_factors_include_all_dimensions(self):
        intake = self._make_intake()
        profile = self._make_profile()
        profiles = ProviderProfile.objects.filter(pk=profile.pk).select_related('client').prefetch_related('target_care_categories')

        results = _build_matching_suggestions_for_intake(intake, profiles)
        factors = results[0]['explanation']['factors']

        for dim in ('specialization', 'urgency', 'care_form', 'region', 'capacity', 'performance'):
            self.assertIn(dim, factors, f"Missing factor: {dim}")
            self.assertIn('status', factors[dim])
            self.assertIn('detail', factors[dim])

    def test_confidence_high_for_strong_match(self):
        """A provider matching urgency, care form, and with good capacity should yield high/medium confidence."""
        intake = self._make_intake()
        profile = self._make_profile(
            offers_outpatient=True,
            handles_medium_urgency=True,
            current_capacity=5,
            max_capacity=10,
            average_wait_days=7,
        )
        profiles = ProviderProfile.objects.filter(pk=profile.pk).select_related('client').prefetch_related('target_care_categories')

        results = _build_matching_suggestions_for_intake(intake, profiles)
        confidence = results[0]['explanation']['confidence']

        self.assertIn(confidence, ('high', 'medium'))

    def test_no_capacity_provider_has_trade_off(self):
        intake = self._make_intake()
        profile = self._make_profile(current_capacity=5, max_capacity=5)
        profiles = ProviderProfile.objects.filter(pk=profile.pk).select_related('client').prefetch_related('target_care_categories')

        results = _build_matching_suggestions_for_intake(intake, profiles)
        trade_offs = results[0]['explanation']['trade_offs']

        self.assertTrue(any('vol' in t.lower() or 'capaciteit' in t.lower() for t in trade_offs))

    def test_long_wait_time_produces_trade_off(self):
        intake = self._make_intake()
        profile = self._make_profile(average_wait_days=60)
        profiles = ProviderProfile.objects.filter(pk=profile.pk).select_related('client').prefetch_related('target_care_categories')

        results = _build_matching_suggestions_for_intake(intake, profiles)
        trade_offs = results[0]['explanation']['trade_offs']

        self.assertTrue(any('wachttijd' in t.lower() for t in trade_offs))

    def test_verify_manually_is_non_empty(self):
        intake = self._make_intake()
        profile = self._make_profile()
        profiles = ProviderProfile.objects.filter(pk=profile.pk).select_related('client').prefetch_related('target_care_categories')

        results = _build_matching_suggestions_for_intake(intake, profiles)
        verify = results[0]['explanation']['verify_manually']

        self.assertIsInstance(verify, list)
        self.assertGreater(len(verify), 0)

    def test_existing_fields_backward_compatible(self):
        """Existing fields must still be present so the dashboard view and template remain unaffected."""
        intake = self._make_intake()
        profile = self._make_profile()
        profiles = ProviderProfile.objects.filter(pk=profile.pk).select_related('client').prefetch_related('target_care_categories')

        results = _build_matching_suggestions_for_intake(intake, profiles)
        result = results[0]

        for field in ('provider_id', 'provider_name', 'match_score', 'fit_score', 'reasons', 'tradeoff', 'free_slots', 'avg_wait_days'):
            self.assertIn(field, result, f"Backward-compat field missing: {field}")
