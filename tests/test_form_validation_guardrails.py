from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase

from contracts.forms import InvoiceForm, TimeEntryForm
from contracts.models import Client, Matter, Organization, OrganizationMembership


User = get_user_model()


class FormValidationGuardrailsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='forms-user', password='testpass123')
        self.org = Organization.objects.create(name='Forms Org', slug='forms-org')
        OrganizationMembership.objects.create(
            organization=self.org,
            user=self.user,
            role=OrganizationMembership.Role.OWNER,
            is_active=True,
        )
        self.client_obj = Client.objects.create(
            organization=self.org,
            name='Forms Client',
            client_type='CORPORATION',
            status='ACTIVE',
            country='United States',
        )
        self.matter = Matter.objects.create(
            organization=self.org,
            client=self.client_obj,
            title='Forms Matter',
            practice_area='CORPORATE',
            status='ACTIVE',
            open_date=date.today(),
        )

    def test_invoice_form_rejects_tax_rate_over_100(self):
        form = InvoiceForm(
            data={
                'client': self.client_obj.id,
                'matter': self.matter.id,
                'issue_date': date.today(),
                'due_date': date.today() + timedelta(days=14),
                'subtotal': '1000.00',
                'tax_rate': '101.00',
                'notes': 'Test',
                'payment_terms': 'Net 30',
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn('tax_rate', form.errors)

    def test_invoice_form_rejects_due_date_before_issue_date(self):
        form = InvoiceForm(
            data={
                'client': self.client_obj.id,
                'matter': self.matter.id,
                'issue_date': date.today(),
                'due_date': date.today() - timedelta(days=1),
                'subtotal': '1000.00',
                'tax_rate': '10.00',
                'notes': 'Test',
                'payment_terms': 'Net 30',
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn('due_date', form.errors)

    def test_time_entry_form_rejects_hours_over_model_limit(self):
        form = TimeEntryForm(
            data={
                'matter': self.matter.id,
                'date': date.today(),
                'hours': '1000.00',
                'description': 'Large invalid hours',
                'activity_type': 'REVIEW',
                'rate': '250.00',
                'is_billable': True,
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn('hours', form.errors)

    def test_time_entry_form_accepts_valid_hours(self):
        form = TimeEntryForm(
            data={
                'matter': self.matter.id,
                'date': date.today(),
                'hours': '2.50',
                'description': 'Valid entry',
                'activity_type': 'REVIEW',
                'rate': '250.00',
                'is_billable': True,
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
