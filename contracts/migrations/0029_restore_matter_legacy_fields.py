from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('contracts', '0028_merge_0016_duediligenceprocess_contract_0027_executivedashboardpreset'),
    ]

    operations = [
        migrations.AddField(
            model_name='matter',
            name='statute_of_limitations',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='matter',
            name='court_name',
            field=models.CharField(blank=True, max_length=200),
        ),
        migrations.AddField(
            model_name='matter',
            name='case_number',
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AddField(
            model_name='matter',
            name='opposing_party',
            field=models.CharField(blank=True, max_length=200),
        ),
        migrations.AddField(
            model_name='matter',
            name='opposing_counsel',
            field=models.CharField(blank=True, max_length=200),
        ),
    ]
