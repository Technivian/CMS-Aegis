from django.core.management import call_command
from django.test import SimpleTestCase


class RequiredChecksAuditTests(SimpleTestCase):
    def test_required_checks_audit_passes(self):
        call_command('audit_required_checks')
