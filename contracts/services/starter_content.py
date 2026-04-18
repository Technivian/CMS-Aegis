from contracts.models import (
    ApprovalRule,
    ClauseCategory,
    ClauseTemplate,
    Counterparty,
    Organization,
    RetentionPolicy,
    Subprocessor,
)


STARTER_COUNTERPARTIES = [
    {
        'name': 'Acme Corporation',
        'entity_type': 'CORPORATION',
        'jurisdiction': 'Delaware, USA',
        'registration_number': '',
        'address': '',
        'contact_name': '',
        'contact_email': '',
        'contact_phone': '',
        'website': '',
        'notes': '',
        'is_active': True,
    },
    {
        'name': 'EuroTech GmbH',
        'entity_type': 'CORPORATION',
        'jurisdiction': 'Germany',
        'registration_number': '',
        'address': '',
        'contact_name': '',
        'contact_email': '',
        'contact_phone': '',
        'website': '',
        'notes': '',
        'is_active': True,
    },
    {
        'name': 'Pacific Holdings Ltd',
        'entity_type': 'LLC',
        'jurisdiction': 'United Kingdom',
        'registration_number': '',
        'address': '',
        'contact_name': '',
        'contact_email': '',
        'contact_phone': '',
        'website': '',
        'notes': '',
        'is_active': True,
    },
]

STARTER_CLAUSE_CATEGORIES = [
    {'name': 'Confidentiality', 'description': 'Non-disclosure and confidentiality provisions', 'order': 0},
    {'name': 'Indemnification', 'description': 'Indemnification and liability clauses', 'order': 1},
    {'name': 'Limitation of Liability', 'description': 'Caps and exclusions on liability', 'order': 2},
    {'name': 'Termination', 'description': 'Termination rights and procedures', 'order': 3},
    {'name': 'Governing Law', 'description': 'Choice of law and jurisdiction', 'order': 4},
    {'name': 'Data Protection', 'description': 'GDPR and data privacy clauses', 'order': 5},
    {'name': 'Force Majeure', 'description': 'Force majeure events and consequences', 'order': 6},
    {'name': 'Intellectual Property', 'description': 'IP ownership and licensing', 'order': 7},
    {'name': 'Dispute Resolution', 'description': 'Arbitration and mediation', 'order': 8},
    {'name': 'Warranties', 'description': 'Representations and warranties', 'order': 9},
]

STARTER_CLAUSE_TEMPLATES = [
    {
        'title': 'Standard NDA Clause (EU)',
        'category_name': 'Confidentiality',
        'content': 'The Receiving Party shall maintain the confidentiality of all Confidential Information and shall not disclose such information to any third party without the prior written consent of the Disclosing Party.',
        'fallback_content': '',
        'jurisdiction_scope': 'EU',
        'is_mandatory': True,
        'applicable_contract_types': '',
        'version': 1,
        'is_approved': True,
        'playbook_notes': '',
        'tags': '',
    },
    {
        'title': 'Standard NDA Clause (US)',
        'category_name': 'Confidentiality',
        'content': 'Recipient agrees to hold in confidence all Confidential Information and to use it solely for the Purpose. Recipient shall not disclose Confidential Information except to its employees who need to know.',
        'fallback_content': '',
        'jurisdiction_scope': 'US',
        'is_mandatory': True,
        'applicable_contract_types': '',
        'version': 1,
        'is_approved': True,
        'playbook_notes': '',
        'tags': '',
    },
    {
        'title': 'GDPR DPA Clause',
        'category_name': 'Data Protection',
        'content': 'The Processor shall process personal data only on documented instructions from the Controller, including with regard to transfers of personal data to a third country or international organisation, pursuant to Article 28 GDPR.',
        'fallback_content': '',
        'jurisdiction_scope': 'EU',
        'is_mandatory': True,
        'applicable_contract_types': '',
        'version': 1,
        'is_approved': True,
        'playbook_notes': '',
        'tags': '',
    },
    {
        'title': 'Standard Indemnification',
        'category_name': 'Indemnification',
        'content': 'Each party shall indemnify, defend, and hold harmless the other party from and against any and all claims, losses, damages, liabilities, and expenses arising out of or relating to any breach of this Agreement.',
        'fallback_content': '',
        'jurisdiction_scope': 'GLOBAL',
        'is_mandatory': False,
        'applicable_contract_types': '',
        'version': 1,
        'is_approved': True,
        'playbook_notes': '',
        'tags': '',
    },
    {
        'title': 'Force Majeure',
        'category_name': 'Force Majeure',
        'content': 'Neither party shall be liable for any failure or delay in performing its obligations where such failure or delay results from force majeure events including but not limited to acts of God, war, terrorism, pandemic, or governmental actions.',
        'fallback_content': '',
        'jurisdiction_scope': 'GLOBAL',
        'is_mandatory': False,
        'applicable_contract_types': '',
        'version': 1,
        'is_approved': True,
        'playbook_notes': '',
        'tags': '',
    },
]

STARTER_SUBPROCESSORS = [
    {
        'name': 'Amazon Web Services',
        'description': '',
        'service_type': 'Cloud Infrastructure',
        'country': 'United States',
        'is_eu_based': False,
        'dpa_in_place': True,
        'scc_in_place': True,
        'dpf_certified': False,
        'data_categories': '',
        'contact_email': '',
        'contract_start_date': None,
        'contract_end_date': None,
        'last_audit_date': None,
        'risk_level': 'LOW',
        'is_active': True,
        'notes': '',
    },
    {
        'name': 'Hetzner',
        'description': '',
        'service_type': 'Cloud Hosting',
        'country': 'Germany',
        'is_eu_based': True,
        'dpa_in_place': True,
        'scc_in_place': False,
        'dpf_certified': False,
        'data_categories': '',
        'contact_email': '',
        'contract_start_date': None,
        'contract_end_date': None,
        'last_audit_date': None,
        'risk_level': 'LOW',
        'is_active': True,
        'notes': '',
    },
    {
        'name': 'Stripe',
        'description': '',
        'service_type': 'Payment Processing',
        'country': 'United States',
        'is_eu_based': False,
        'dpa_in_place': True,
        'scc_in_place': True,
        'dpf_certified': False,
        'data_categories': '',
        'contact_email': '',
        'contract_start_date': None,
        'contract_end_date': None,
        'last_audit_date': None,
        'risk_level': 'LOW',
        'is_active': True,
        'notes': '',
    },
]

STARTER_RETENTION_POLICIES = [
    {
        'title': 'Contract Documents',
        'category': 'CONTRACTS',
        'description': '',
        'retention_period_days': 2555,
        'legal_basis': '',
        'deletion_method': '',
        'auto_delete': False,
        'review_frequency_days': 365,
        'last_reviewed': None,
        'next_review': None,
        'is_active': True,
    },
    {
        'title': 'Client Personal Data',
        'category': 'CLIENT_DATA',
        'description': '',
        'retention_period_days': 1825,
        'legal_basis': '',
        'deletion_method': '',
        'auto_delete': False,
        'review_frequency_days': 365,
        'last_reviewed': None,
        'next_review': None,
        'is_active': True,
    },
    {
        'title': 'Financial Records',
        'category': 'FINANCIAL',
        'description': '',
        'retention_period_days': 2555,
        'legal_basis': '',
        'deletion_method': '',
        'auto_delete': False,
        'review_frequency_days': 365,
        'last_reviewed': None,
        'next_review': None,
        'is_active': True,
    },
    {
        'title': 'Email Correspondence',
        'category': 'CORRESPONDENCE',
        'description': '',
        'retention_period_days': 730,
        'legal_basis': '',
        'deletion_method': '',
        'auto_delete': False,
        'review_frequency_days': 365,
        'last_reviewed': None,
        'next_review': None,
        'is_active': True,
    },
]

STARTER_APPROVAL_RULES = [
    {
        'name': 'High Value Contract',
        'description': '',
        'trigger_type': 'VALUE_ABOVE',
        'trigger_value': '100000',
        'approval_step': 'FINANCE',
        'approver_role': 'PARTNER',
        'sla_hours': 48,
        'escalation_after_hours': 72,
        'is_active': True,
        'order': 0,
    },
    {
        'name': 'EU Jurisdiction',
        'description': '',
        'trigger_type': 'JURISDICTION',
        'trigger_value': 'EU',
        'approval_step': 'PRIVACY',
        'approver_role': 'SENIOR_ASSOCIATE',
        'sla_hours': 48,
        'escalation_after_hours': 72,
        'is_active': True,
        'order': 0,
    },
    {
        'name': 'Data Transfer Review',
        'description': '',
        'trigger_type': 'DATA_TRANSFER',
        'trigger_value': 'true',
        'approval_step': 'PRIVACY',
        'approver_role': 'PARTNER',
        'sla_hours': 48,
        'escalation_after_hours': 72,
        'is_active': True,
        'order': 0,
    },
    {
        'name': 'High Risk Approval',
        'description': '',
        'trigger_type': 'RISK_LEVEL',
        'trigger_value': 'HIGH',
        'approval_step': 'LEGAL',
        'approver_role': 'PARTNER',
        'sla_hours': 48,
        'escalation_after_hours': 72,
        'is_active': True,
        'order': 0,
    },
]


def ensure_org_starter_content(organization: Organization) -> None:
    for counterparty in STARTER_COUNTERPARTIES:
        Counterparty.objects.get_or_create(
            organization=organization,
            name=counterparty['name'],
            defaults=counterparty,
        )

    categories_by_name = {}
    for category in STARTER_CLAUSE_CATEGORIES:
        category_obj, _ = ClauseCategory.objects.get_or_create(
            organization=organization,
            name=category['name'],
            defaults=category,
        )
        categories_by_name[category['name']] = category_obj

    for template in STARTER_CLAUSE_TEMPLATES:
        template_defaults = {k: v for k, v in template.items() if k != 'category_name'}
        template_defaults['category'] = categories_by_name[template['category_name']]
        ClauseTemplate.objects.get_or_create(
            organization=organization,
            title=template['title'],
            defaults=template_defaults,
        )

    for subprocessor in STARTER_SUBPROCESSORS:
        Subprocessor.objects.get_or_create(
            organization=organization,
            name=subprocessor['name'],
            defaults=subprocessor,
        )

    for policy in STARTER_RETENTION_POLICIES:
        RetentionPolicy.objects.get_or_create(
            organization=organization,
            title=policy['title'],
            defaults=policy,
        )

    for rule in STARTER_APPROVAL_RULES:
        ApprovalRule.objects.get_or_create(
            organization=organization,
            name=rule['name'],
            defaults=rule,
        )
