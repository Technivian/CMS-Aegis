from django.test import TestCase
from django.contrib.auth import get_user_model
from .tenancy import ensure_user_organization
from .models import RiskLog, ComplianceChecklist, ChecklistItem, Contract

User = get_user_model()

class Phase5ModelTests(TestCase):

    def setUp(self):
        """Set up non-modified objects used by all test methods."""
        self.user = User.objects.create_user(username='testuser', password='testpassword')
        org = ensure_user_organization(self.user)
        self.contract = Contract.objects.create(title='Test Contract', created_by=self.user, organization=org)

    def test_create_risk_log(self):
        """Test that a RiskLog can be created."""
        risk = RiskLog.objects.create(
            title='Test Risk',
            description='A test risk description.',
            created_by=self.user,
            contract=self.contract,
            mitigation_plan='Take test steps.'
        )
        self.assertIsNotNone(risk)
        self.assertEqual(risk.risk_level, 'MEDIUM')
        self.assertEqual(risk.contract, self.contract)
        self.assertEqual(str(risk), 'Test Risk')

    def test_create_compliance_checklist(self):
        """Test that a ComplianceChecklist can be created."""
        checklist = ComplianceChecklist.objects.create(
            title='Test Checklist',
            description='Checklist description',
            regulation_type=ComplianceChecklist.RegulationType.OTHER,
            contract=self.contract,
            created_by=self.user,
        )
        self.assertIsNotNone(checklist)
        self.assertEqual(checklist.regulation_type, ComplianceChecklist.RegulationType.OTHER)
        self.assertEqual(str(checklist), 'Test Checklist')

    def test_create_checklist_item(self):
        """Test that a ChecklistItem can be created and linked to a checklist."""
        checklist = ComplianceChecklist.objects.create(
            title='Test Checklist for Items',
            description='Checklist description',
            regulation_type=ComplianceChecklist.RegulationType.OTHER,
        )
        item = ChecklistItem.objects.create(
            checklist=checklist,
            title='Test item 1'
        )
        self.assertIsNotNone(item)
        self.assertEqual(item.is_completed, False)
        self.assertEqual(item.checklist, checklist)
        self.assertEqual(str(item), 'Test item 1')
        self.assertEqual(checklist.items.count(), 1)
