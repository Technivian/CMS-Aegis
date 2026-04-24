from decimal import Decimal

from django.db import migrations, models
from django.db.models import deletion


def forwards(apps, schema_editor):
    Client = apps.get_model('contracts', 'Client')
    TrustAccount = apps.get_model('contracts', 'TrustAccount')

    default_client = Client.objects.order_by('id').first()
    if default_client is None:
        default_client = Client.objects.create(
            name='General Trust Client',
            client_type='OTHER',
            status='ACTIVE',
            email='',
            phone='',
            address='',
            city='',
            state='',
            zip_code='',
            country='United States',
            tax_id='',
            website='',
            industry='',
            notes='',
            primary_contact='',
            primary_contact_email='',
            primary_contact_phone='',
            responsible_attorney=None,
            originating_attorney=None,
            created_by=None,
        )

    for account in TrustAccount.objects.all():
        account.account_name = account.account_name or f'Trust Account {account.id}'
        account.balance = getattr(account, 'balance', None) or Decimal('0')
        account.client_id = account.client_id or default_client.id
        account.save(update_fields=['account_name', 'balance', 'client'])


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ('contracts', '0032_restore_deadline_task_type'),
    ]

    operations = [
        migrations.AddField(
            model_name='trustaccount',
            name='account_name',
            field=models.CharField(blank=True, default='', max_length=200),
        ),
        migrations.AddField(
            model_name='trustaccount',
            name='balance',
            field=models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=12),
        ),
        migrations.AddField(
            model_name='trustaccount',
            name='matter',
            field=models.ForeignKey(blank=True, null=True, on_delete=deletion.CASCADE, related_name='trust_accounts', to='contracts.matter'),
        ),
        migrations.AddField(
            model_name='trustaccount',
            name='client',
            field=models.ForeignKey(blank=True, null=True, on_delete=deletion.CASCADE, related_name='trust_accounts', to='contracts.client'),
        ),
        migrations.RunPython(forwards, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='trustaccount',
            name='account_name',
            field=models.CharField(max_length=200),
        ),
        migrations.AlterField(
            model_name='trustaccount',
            name='client',
            field=models.ForeignKey(on_delete=deletion.CASCADE, related_name='trust_accounts', to='contracts.client'),
        ),
    ]
