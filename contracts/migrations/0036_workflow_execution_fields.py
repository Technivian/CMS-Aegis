from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('contracts', '0035_add_search_preset_notification_indexes'),
    ]

    operations = [
        migrations.AddField(
            model_name='workflowtemplatestep',
            name='assignee_role',
            field=models.CharField(blank=True, choices=[('PARTNER', 'Partner'), ('SENIOR_ASSOCIATE', 'Senior Associate'), ('ASSOCIATE', 'Associate'), ('PARALEGAL', 'Paralegal'), ('LEGAL_ASSISTANT', 'Legal Assistant'), ('ADMIN', 'Administrator'), ('CLIENT', 'Client')], max_length=20),
        ),
        migrations.AddField(
            model_name='workflowtemplatestep',
            name='condition_expression',
            field=models.CharField(blank=True, help_text='Example: value>=250000 or data_transfer=true', max_length=255),
        ),
        migrations.AddField(
            model_name='workflowtemplatestep',
            name='escalation_after_hours',
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='workflowtemplatestep',
            name='sla_hours',
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='workflowtemplatestep',
            name='specific_assignee',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='workflow_template_step_assignments', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='workflowtemplatestep',
            name='step_kind',
            field=models.CharField(choices=[('TASK', 'Task'), ('APPROVAL', 'Approval'), ('AUTOMATIC', 'Automatic'), ('BRANCH', 'Branch')], default='TASK', max_length=20),
        ),
        migrations.AddField(
            model_name='workflowstep',
            name='blocked_reason',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='workflowstep',
            name='escalated_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='workflowstep',
            name='template_step',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='workflow_steps', to='contracts.workflowtemplatestep'),
        ),
        migrations.AlterField(
            model_name='workflowstep',
            name='status',
            field=models.CharField(choices=[('PENDING', 'Pending'), ('IN_PROGRESS', 'In Progress'), ('COMPLETED', 'Completed'), ('SKIPPED', 'Skipped'), ('ESCALATED', 'Escalated')], default='PENDING', max_length=20),
        ),
        migrations.AddIndex(
            model_name='workflowstep',
            index=models.Index(fields=['workflow', 'status', 'due_date'], name='workflow_step_stat_due_ix'),
        ),
    ]
