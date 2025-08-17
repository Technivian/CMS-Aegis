from django.test import TestCase
from django.contrib.auth import get_user_model
from .models import RiskLog, ComplianceChecklist, ChecklistItem, Contract

User = get_user_model()

class Phase5ModelTests(TestCase):

    def setUp(self):
        """Set up non-modified objects used by all test methods."""
        self.user = User.objects.create_user(username='testuser', password='testpassword')
        self.contract = Contract.objects.create(title='Test Contract', created_by=self.user)

    def test_create_risk_log(self):
        """Test that a RiskLog can be created."""
        risk = RiskLog.objects.create(
            title='Test Risk',
            description='A test risk description.',
            owner=self.user,
            linked_contract=self.contract,
            mitigation_steps='Take test steps.'
        )
        self.assertIsNotNone(risk)
        self.assertEqual(risk.risk_level, 'MEDIUM')
        self.assertEqual(risk.mitigation_status, 'PENDING')
        self.assertEqual(str(risk), 'Test Risk')

    def test_create_compliance_checklist(self):
        """Test that a ComplianceChecklist can be created."""
        checklist = ComplianceChecklist.objects.create(
            name='Test Checklist',
            regulation='Test Regulation 123',
            reviewed_by=self.user
        )
        self.assertIsNotNone(checklist)
        self.assertEqual(checklist.status, 'NOT_STARTED')
        self.assertEqual(str(checklist), 'Test Checklist')

    def test_create_checklist_item(self):
        """Test that a ChecklistItem can be created and linked to a checklist."""
        checklist = ComplianceChecklist.objects.create(
            name='Test Checklist for Items',
            regulation='Test Regulation 456'
        )
        item = ChecklistItem.objects.create(
            checklist=checklist,
            text='Test item 1'
        )
        self.assertIsNotNone(item)
        self.assertEqual(item.is_checked, False)
        self.assertEqual(item.checklist, checklist)
        self.assertEqual(str(item), 'Test item 1')
        self.assertEqual(checklist.items.count(), 1)
