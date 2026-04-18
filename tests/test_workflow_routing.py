from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from contracts.models import ApprovalRequest, ApprovalRule, Contract, Organization, OrganizationMembership, UserProfile, Workflow, WorkflowTemplate
from contracts.services.workflow_routing import build_approval_request_plan_for_contract, suggest_workflow_category_for_contract


User = get_user_model()


class WorkflowRoutingTests(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(name='Workflow Org', slug='workflow-org')
        self.user = User.objects.create_user(username='workflow-user', password='testpass123')
        OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.user,
            role=OrganizationMembership.Role.OWNER,
            is_active=True,
        )
        UserProfile.objects.get_or_create(user=self.user, defaults={'role': UserProfile.Role.ADMIN})

        self.contract_review_template = WorkflowTemplate.objects.create(
            name='Contract Review',
            description='Standard contract review flow',
            category=WorkflowTemplate.Category.CONTRACT_REVIEW,
            is_active=True,
        )
        self.compliance_template = WorkflowTemplate.objects.create(
            name='Compliance Review',
            description='High-risk compliance flow',
            category=WorkflowTemplate.Category.COMPLIANCE,
            is_active=True,
        )
        self.due_diligence_template = WorkflowTemplate.objects.create(
            name='Due Diligence',
            description='High value review flow',
            category=WorkflowTemplate.Category.DUE_DILIGENCE,
            is_active=True,
        )

        self.approval_rule = ApprovalRule.objects.create(
            organization=self.organization,
            name='License review',
            trigger_type=ApprovalRule.TriggerType.CONTRACT_TYPE,
            trigger_value=Contract.ContractType.LICENSE,
            approval_step='LEGAL',
            approver_role=UserProfile.Role.ADMIN,
            specific_approver=self.user,
            sla_hours=24,
            escalation_after_hours=48,
            order=1,
        )

    def test_suggest_workflow_category_uses_contract_type_value_and_jurisdiction(self):
        compliance_contract = Contract.objects.create(
            organization=self.organization,
            title='EU DPA',
            contract_type=Contract.ContractType.NDA,
            status=Contract.Status.ACTIVE,
            counterparty='Acme',
            governing_law='Germany',
            jurisdiction='EU',
            data_transfer_flag=True,
            created_by=self.user,
        )
        high_value_contract = Contract.objects.create(
            organization=self.organization,
            title='High Value MSA',
            contract_type=Contract.ContractType.MSA,
            status=Contract.Status.ACTIVE,
            counterparty='Acme',
            governing_law='Delaware',
            jurisdiction='New York',
            value=500000,
            created_by=self.user,
        )
        standard_contract = Contract.objects.create(
            organization=self.organization,
            title='Standard NDA',
            contract_type=Contract.ContractType.NDA,
            status=Contract.Status.ACTIVE,
            counterparty='Acme',
            governing_law='Delaware',
            jurisdiction='New York',
            created_by=self.user,
        )

        self.assertEqual(suggest_workflow_category_for_contract(compliance_contract), WorkflowTemplate.Category.COMPLIANCE)
        self.assertEqual(suggest_workflow_category_for_contract(high_value_contract), WorkflowTemplate.Category.DUE_DILIGENCE)
        self.assertEqual(suggest_workflow_category_for_contract(standard_contract), WorkflowTemplate.Category.CONTRACT_REVIEW)

    def test_workflow_create_auto_selects_template(self):
        self.client.login(username='workflow-user', password='testpass123')
        contract = Contract.objects.create(
            organization=self.organization,
            title='High Value License',
            contract_type=Contract.ContractType.LICENSE,
            status=Contract.Status.ACTIVE,
            counterparty='Acme',
            governing_law='Delaware',
            jurisdiction='EU',
            value=300000,
            data_transfer_flag=True,
            created_by=self.user,
        )

        response = self.client.post(
            reverse('contracts:workflow_create'),
            data={
                'title': 'Routing Workflow',
                'description': 'Auto-routed workflow',
                'contract': contract.id,
                'template': '',
            },
        )

        self.assertEqual(response.status_code, 302)
        workflow = Workflow.objects.get(title='Routing Workflow')
        self.assertEqual(workflow.template_id, self.compliance_template.id)

    def test_workflow_create_creates_approval_request_plan(self):
        self.client.login(username='workflow-user', password='testpass123')
        contract = Contract.objects.create(
            organization=self.organization,
            title='License Workflow Contract',
            contract_type=Contract.ContractType.LICENSE,
            status=Contract.Status.ACTIVE,
            counterparty='Acme',
            governing_law='Delaware',
            jurisdiction='New York',
            value=300000,
            created_by=self.user,
        )

        response = self.client.post(
            reverse('contracts:workflow_create'),
            data={
                'title': 'Approval Routing Workflow',
                'description': 'Creates approval request plan',
                'contract': contract.id,
                'template': '',
            },
        )

        self.assertEqual(response.status_code, 302)
        approval_request = ApprovalRequest.objects.get(contract=contract, rule=self.approval_rule)
        self.assertEqual(approval_request.assigned_to_id, self.user.id)
        self.assertEqual(approval_request.status, ApprovalRequest.Status.PENDING)

    def test_approval_request_plan_parses_currency_thresholds(self):
        threshold_rule = ApprovalRule.objects.create(
            organization=self.organization,
            name='Value review',
            trigger_type=ApprovalRule.TriggerType.VALUE_ABOVE,
            trigger_value='$250,000',
            approval_step='FINANCE',
            approver_role=UserProfile.Role.ADMIN,
            specific_approver=self.user,
            sla_hours=48,
            escalation_after_hours=72,
            order=2,
        )
        contract = Contract.objects.create(
            organization=self.organization,
            title='High Value Contract',
            contract_type=Contract.ContractType.MSA,
            status=Contract.Status.ACTIVE,
            counterparty='Acme',
            governing_law='Delaware',
            jurisdiction='New York',
            value=300000,
            created_by=self.user,
        )

        plan = build_approval_request_plan_for_contract(contract)

        self.assertEqual({item['rule'].id for item in plan}, {threshold_rule.id})
        self.assertEqual(plan[0]['assigned_to'].id, self.user.id)
