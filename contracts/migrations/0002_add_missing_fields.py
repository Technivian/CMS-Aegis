
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('contracts', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='contract',
            name='counterparty',
            field=models.CharField(blank=True, max_length=200),
        ),
        migrations.AddField(
            model_name='contract',
            name='value',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True),
        ),
        migrations.AddField(
            model_name='contract',
            name='start_date',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='contract',
            name='end_date',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='contract',
            name='created_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=models.deletion.SET_NULL, to='auth.user'),
        ),
        migrations.AlterField(
            model_name='contract',
            name='content',
            field=models.TextField(blank=True),
        ),
        migrations.AlterField(
            model_name='contract',
            name='status',
            field=models.CharField(choices=[('DRAFT', 'Draft'), ('PENDING', 'Pending'), ('ACTIVE', 'Active'), ('COMPLETED', 'Completed'), ('CANCELLED', 'Cancelled')], default='DRAFT', max_length=20),
        ),
    ]
