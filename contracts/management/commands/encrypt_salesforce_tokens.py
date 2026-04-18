from django.core.management.base import BaseCommand

from contracts.models import SalesforceOrganizationConnection
from contracts.services.salesforce import TOKEN_CIPHER_PREFIX, decrypt_salesforce_token, encrypt_salesforce_token


class Command(BaseCommand):
    help = 'Encrypt existing Salesforce connection tokens at rest.'

    def handle(self, *args, **options):
        updated = 0
        for connection in SalesforceOrganizationConnection.objects.all():
            access_token = decrypt_salesforce_token(connection.access_token)
            refresh_token = decrypt_salesforce_token(connection.refresh_token)
            new_access = encrypt_salesforce_token(access_token) if access_token else ''
            new_refresh = encrypt_salesforce_token(refresh_token) if refresh_token else ''
            if connection.access_token != new_access or connection.refresh_token != new_refresh:
                connection.access_token = new_access
                connection.refresh_token = new_refresh
                connection.save(update_fields=['access_token', 'refresh_token', 'updated_at'])
                updated += 1
        self.stdout.write(
            self.style.SUCCESS(
                f'Encrypted Salesforce tokens for {updated} connection(s); prefix={TOKEN_CIPHER_PREFIX}'
            )
        )
