from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase

from contracts.models import ClauseCategory, Contract, Organization, OrganizationMembership
from contracts.services.clauses import ClauseService
from contracts.services.obligations import ObligationService
from contracts.services.templates import TemplateService


User = get_user_model()


class PersistedServicesTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="svc_user", password="pass12345")
        self.org = Organization.objects.create(name="Service Org", slug="service-org")
        OrganizationMembership.objects.create(
            organization=self.org,
            user=self.user,
            role=OrganizationMembership.Role.OWNER,
            is_active=True,
        )
        self.contract = Contract.objects.create(
            organization=self.org,
            title="Service Contract",
            content="Persist me",
            status=Contract.Status.ACTIVE,
            created_by=self.user,
        )

    def test_template_service_is_persisted(self):
        service = TemplateService(organization=self.org)
        created = service.create_template(
            title="Master Services Template",
            content="MSA body",
            category="general",
            tags=["msa", "vendor"],
        )

        # New service instance should still see the same row (no in-memory singleton state).
        fetched = TemplateService(organization=self.org).get_template(created.id)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.title, "Master Services Template")
        self.assertEqual(fetched.content, "MSA body")

    def test_clause_service_is_persisted_and_tag_searchable(self):
        service = ClauseService(organization=self.org)
        clause = service.create_clause(
            title="Liability Cap",
            content="Liability is capped",
            category="liability",
            tags=["risk", "liability"],
        )

        self.assertTrue(ClauseCategory.objects.filter(organization=self.org, name="liability").exists())

        matched = ClauseService(organization=self.org).search_clauses(tags=["risk"])
        self.assertEqual(len(matched), 1)
        self.assertEqual(matched[0].id, clause.id)

    def test_obligation_service_is_persisted_and_status_updates(self):
        due = (date.today() + timedelta(days=10)).isoformat()
        service = ObligationService(organization=self.org)
        obligation = service.create_obligation(
            title="Renewal Review",
            description="Review renewal terms",
            due_date=due,
            contract_id=str(self.contract.pk),
            assigned_to=self.user.username,
            priority="high",
        )

        persisted = ObligationService(organization=self.org).list_obligations(contract_id=str(self.contract.pk))
        self.assertEqual(len(persisted), 1)
        self.assertEqual(persisted[0].id, obligation.id)
        self.assertEqual(persisted[0].status, "pending")

        updated = service.update_obligation(obligation.id, status="completed")
        self.assertIsNotNone(updated)
        self.assertEqual(updated.status, "completed")
