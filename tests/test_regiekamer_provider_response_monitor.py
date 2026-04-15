from datetime import date, timedelta

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from contracts.models import (
    CaseIntakeProcess,
    Client as CareProvider,
    Organization,
    OrganizationMembership,
    PlacementRequest,
)
from contracts.views import build_provider_response_monitor


class RegiekamerProviderResponseMonitorTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='monitor_owner',
            email='monitor_owner@example.com',
            password='testpass123',
        )
        self.organization = Organization.objects.create(name='Monitor Org', slug='monitor-org')
        OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.user,
            role=OrganizationMembership.Role.OWNER,
            is_active=True,
        )
        self.provider = CareProvider.objects.create(
            organization=self.organization,
            name='Monitor Provider',
            status=CareProvider.Status.ACTIVE,
            created_by=self.user,
        )
        self.client.login(username='monitor_owner', password='testpass123')

    def _create_case(self, title, *, status=CaseIntakeProcess.ProcessStatus.MATCHING, urgency=CaseIntakeProcess.Urgency.MEDIUM):
        return CaseIntakeProcess.objects.create(
            organization=self.organization,
            title=title,
            status=status,
            urgency=urgency,
            preferred_care_form=CaseIntakeProcess.CareForm.OUTPATIENT,
            start_date=date.today(),
            target_completion_date=date.today() + timedelta(days=7),
            case_coordinator=self.user,
            assessment_summary='Samenvatting aanwezig.',
            client_age_category=CaseIntakeProcess.AgeCategory.ADULT,
        )

    def _create_placement(self, intake, provider_response_status, *, requested_days_ago=1, deadline_days_after_request=3):
        requested_at = timezone.now() - timedelta(days=requested_days_ago)
        deadline_at = requested_at + timedelta(days=deadline_days_after_request)
        return PlacementRequest.objects.create(
            due_diligence_process=intake,
            status=PlacementRequest.Status.IN_REVIEW,
            proposed_provider=self.provider,
            selected_provider=self.provider,
            care_form=intake.preferred_care_form,
            provider_response_status=provider_response_status,
            provider_response_requested_at=requested_at,
            provider_response_deadline_at=deadline_at,
        )

    def test_monitor_page_renders_with_counters_and_queue(self):
        intake = self._create_case('Casus Monitor Pagina')
        self._create_placement(intake, PlacementRequest.ProviderResponseStatus.PENDING, requested_days_ago=2)

        response = self.client.get(reverse('careon:provider_response_monitor'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Provider Response Monitor')
        self.assertContains(response, 'Actiequeue providerreacties')
        self.assertContains(response, 'Open plaatsing')
        self.assertContains(response, f"{reverse('careon:case_detail', kwargs={'pk': intake.pk})}?tab=plaatsing")

    def test_monitor_summary_counts_mixed_scenarios(self):
        waiting_intake = self._create_case('Casus Wachtend')
        overdue_intake = self._create_case('Casus Overdue')
        waitlist_intake = self._create_case('Casus Wachtlijst')
        rejected_intake = self._create_case('Casus Afgewezen')

        self._create_placement(waiting_intake, PlacementRequest.ProviderResponseStatus.PENDING, requested_days_ago=1)
        self._create_placement(overdue_intake, PlacementRequest.ProviderResponseStatus.PENDING, requested_days_ago=5, deadline_days_after_request=1)
        self._create_placement(waitlist_intake, PlacementRequest.ProviderResponseStatus.WAITLIST, requested_days_ago=4)
        self._create_placement(rejected_intake, PlacementRequest.ProviderResponseStatus.REJECTED, requested_days_ago=2)

        monitor = build_provider_response_monitor(self.organization)
        summary = monitor['summary']

        self.assertEqual(summary['waiting_count'], 2)
        self.assertEqual(summary['overdue_count'], 2)
        self.assertEqual(summary['rematch_recommended_count'], 2)
        self.assertEqual(summary['waitlist_no_capacity_count'], 1)
        self.assertEqual(summary['avg_age_days'], 3.0)
        self.assertEqual(summary['total_cases'], 4)

    def test_monitor_excludes_accepted_and_completed_case_items(self):
        accepted_intake = self._create_case('Casus Geaccepteerd')
        completed_intake = self._create_case('Casus Completed', status=CaseIntakeProcess.ProcessStatus.COMPLETED)
        monitored_intake = self._create_case('Casus In Monitor')

        self._create_placement(accepted_intake, PlacementRequest.ProviderResponseStatus.ACCEPTED, requested_days_ago=2)
        self._create_placement(completed_intake, PlacementRequest.ProviderResponseStatus.PENDING, requested_days_ago=2)
        self._create_placement(monitored_intake, PlacementRequest.ProviderResponseStatus.NO_CAPACITY, requested_days_ago=3)

        monitor = build_provider_response_monitor(self.organization)
        titles = [row['case_title'] for row in monitor['queue_rows']]

        self.assertIn('Casus In Monitor', titles)
        self.assertNotIn('Casus Geaccepteerd', titles)
        self.assertNotIn('Casus Completed', titles)

    def test_monitor_uses_latest_placement_per_case(self):
        intake = self._create_case('Casus Laatste Plaatsing')

        self._create_placement(
            intake,
            PlacementRequest.ProviderResponseStatus.REJECTED,
            requested_days_ago=8,
            deadline_days_after_request=2,
        )
        latest = self._create_placement(
            intake,
            PlacementRequest.ProviderResponseStatus.PENDING,
            requested_days_ago=2,
            deadline_days_after_request=4,
        )

        monitor = build_provider_response_monitor(self.organization)

        self.assertEqual(len(monitor['queue_rows']), 1)
        row = monitor['queue_rows'][0]
        self.assertEqual(row['case_title'], 'Casus Laatste Plaatsing')
        self.assertEqual(row['status'], PlacementRequest.ProviderResponseStatus.PENDING)
        self.assertEqual(row['provider_name'], latest.selected_provider.name)

    def test_monitor_normalizes_legacy_no_response_alias(self):
        intake = self._create_case('Casus Legacy Alias')
        self._create_placement(intake, 'NO_RESPONSE', requested_days_ago=4, deadline_days_after_request=2)

        monitor = build_provider_response_monitor(self.organization)

        self.assertEqual(len(monitor['queue_rows']), 1)
        row = monitor['queue_rows'][0]
        self.assertEqual(row['status'], PlacementRequest.ProviderResponseStatus.PENDING)
        self.assertTrue(row['flags']['is_waiting'])

    def test_monitor_rows_deep_link_to_case_placement_tab(self):
        intake = self._create_case('Casus Deep Link')
        self._create_placement(intake, PlacementRequest.ProviderResponseStatus.NEEDS_INFO, requested_days_ago=3)

        response = self.client.get(reverse('careon:provider_response_monitor'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f"{reverse('careon:case_detail', kwargs={'pk': intake.pk})}?tab=plaatsing")
