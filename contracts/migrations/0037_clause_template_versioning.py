from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('contracts', '0036_workflow_execution_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='clausetemplate',
            name='parent_template',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='derived_versions', to='contracts.clausetemplate'),
        ),
    ]
