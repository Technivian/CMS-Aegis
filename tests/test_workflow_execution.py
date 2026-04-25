from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from contracts.models import Contract, Notification, Organization, OrganizationMembership, UserProfile, Workflow, WorkflowStep, WorkflowTemplate, WorkflowTemplateStep


User = get_user_model()


class WorkflowExecutionTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='wf-owner', password='testpass123')
        self.admin = User.objects.create_user(username='wf-admin', password='testpass123')
        self.member = User.objects.create_user(username='wf-member', password='testpass123')

        self.organization = Organization.objects.create(name='Workflow Power Org', slug='workflow-power-org')
        OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.owner,
            role=OrganizationMembership.Role.OWNER,
            is_active=True,
        )
        OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.admin,
            role=OrganizationMembership.Role.ADMIN,
            is_active=True,
        )
        OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.member,
            role=OrganizationMembership.Role.MEMBER,
            is_active=True,
        )
        UserProfile.objects.get_or_create(user=self.owner, defaults={'role': UserProfile.Role.ADMIN})
        UserProfile.objects.get_or_create(user=self.admin, defaults={'role': UserProfile.Role.ADMIN})
        UserProfile.objects.get_or_create(user=self.member, defaults={'role': UserProfile.Role.ASSOCIATE})

        self.template = WorkflowTemplate.objects.create(
            name='Power Workflow',
            description='Branching and routing workflow',
            category=WorkflowTemplate.Category.CONTRACT_REVIEW,
            is_active=True,
        )
        WorkflowTemplateStep.objects.create(
            template=self.template,
            name='Draft Review',
            description='Initial review',
            order=1,
            step_kind=WorkflowTemplateStep.StepKind.TASK,
            sla_hours=12,
        )
        WorkflowTemplateStep.objects.create(
            template=self.template,
            name='High Value Approval',
            description='Only for high value contracts',
            order=2,
            step_kind=WorkflowTemplateStep.StepKind.APPROVAL,
            condition_expression='value>=250000',
            assignee_role=UserProfile.Role.ADMIN,
            sla_hours=24,
            escalation_after_hours=48,
        )
        WorkflowTemplateStep.objects.create(
            template=self.template,
            name='Auto Archive',
            description='Complete automatically',
            order=3,
            step_kind=WorkflowTemplateStep.StepKind.AUTOMATIC,
        )

        self.high_value_contract = Contract.objects.create(
            organization=self.organization,
            title='High Value Contract',
            contract_type=Contract.ContractType.MSA,
            status=Contract.Status.ACTIVE,
            counterparty='Acme',
            governing_law='Delaware',
            jurisdiction='New York',
            value=500000,
            created_by=self.owner,
        )
        self.low_value_contract = Contract.objects.create(
            organization=self.organization,
            title='Low Value Contract',
            contract_type=Contract.ContractType.NDA,
            status=Contract.Status.ACTIVE,
            counterparty='Acme',
            governing_law='Delaware',
            jurisdiction='New York',
            value=5000,
            created_by=self.owner,
        )

    def test_workflow_create_materializes_template_steps_and_skips_branches(self):
        self.assertTrue(self.client.login(username='wf-owner', password='testpass123'))
        response = self.client.post(
            reverse('contracts:workflow_create'),
            data={
                'title': 'High Value Routing Workflow',
                'description': 'Runtime workflow seeded from template',
                'contract': self.high_value_contract.id,
                'template': self.template.id,
            },
        )
        self.assertEqual(response.status_code, 302)
        workflow = Workflow.objects.get(title='High Value Routing Workflow')
        steps = list(workflow.steps.order_by('order'))
        self.assertEqual(len(steps), 3)
        self.assertEqual(steps[0].status, WorkflowStep.Status.IN_PROGRESS)
        self.assertIsNotNone(steps[0].due_date)
        self.assertEqual(steps[1].status, WorkflowStep.Status.PENDING)
        self.assertEqual(steps[1].assigned_to_id, self.admin.id)
        self.assertEqual(steps[2].status, WorkflowStep.Status.COMPLETED)
        self.assertIsNotNone(steps[2].completed_at)

        response = self.client.post(
            reverse('contracts:workflow_create'),
            data={
                'title': 'Low Value Routing Workflow',
                'description': 'Runtime workflow seeded from template',
                'contract': self.low_value_contract.id,
                'template': self.template.id,
            },
        )
        self.assertEqual(response.status_code, 302)
        workflow = Workflow.objects.get(title='Low Value Routing Workflow')
        steps = list(workflow.steps.order_by('order'))
        self.assertEqual(steps[0].status, WorkflowStep.Status.IN_PROGRESS)
        self.assertEqual(steps[1].status, WorkflowStep.Status.SKIPPED)
        self.assertIn('Condition', steps[1].blocked_reason)

    def test_workflow_step_completion_activates_next_step(self):
        self.assertTrue(self.client.login(username='wf-owner', password='testpass123'))
        workflow = Workflow.objects.create(
            organization=self.organization,
            title='Manual Progress Workflow',
            description='Manual workflow',
            contract=self.high_value_contract,
            template=self.template,
            created_by=self.owner,
        )
        first = WorkflowStep.objects.create(
            workflow=workflow,
            template_step=self.template.steps.get(order=1),
            name='Draft Review',
            status=WorkflowStep.Status.IN_PROGRESS,
            due_date=timezone.now() + timedelta(hours=6),
            order=1,
        )
        second = WorkflowStep.objects.create(
            workflow=workflow,
            template_step=self.template.steps.get(order=2),
            name='High Value Approval',
            status=WorkflowStep.Status.PENDING,
            order=2,
        )

        response = self.client.post(reverse('contracts:workflow_step_complete', args=[first.id]))
        self.assertEqual(response.status_code, 302)

        first.refresh_from_db()
        second.refresh_from_db()
        workflow.refresh_from_db()
        self.assertEqual(first.status, WorkflowStep.Status.COMPLETED)
        self.assertEqual(second.status, WorkflowStep.Status.IN_PROGRESS)
        self.assertEqual(workflow.status, Workflow.Status.ACTIVE)

    def test_overdue_workflow_step_escalates_and_notifies(self):
        self.assertTrue(self.client.login(username='wf-owner', password='testpass123'))
        workflow = Workflow.objects.create(
            organization=self.organization,
            title='Overdue Workflow',
            description='Overdue workflow',
            contract=self.high_value_contract,
            template=self.template,
            created_by=self.owner,
        )
        step = WorkflowStep.objects.create(
            workflow=workflow,
            template_step=self.template.steps.get(order=2),
            name='High Value Approval',
            status=WorkflowStep.Status.IN_PROGRESS,
            assigned_to=self.admin,
            due_date=timezone.now() - timedelta(hours=1),
            order=2,
        )

        call_command('send_contract_reminders')

        step.refresh_from_db()
        self.assertEqual(step.status, WorkflowStep.Status.ESCALATED)
        self.assertIsNotNone(step.escalated_at)
        self.assertTrue(
            Notification.objects.filter(
                recipient=self.admin,
                notification_type=Notification.NotificationType.TASK,
                title__startswith='Workflow overdue:',
            ).exists()
        )
