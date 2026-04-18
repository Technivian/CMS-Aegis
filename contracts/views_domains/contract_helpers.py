from django.db.models import Q
from django.utils import timezone

from contracts.models import ClauseTemplate, Contract, OrganizationMembership


def _extract_valid_mentions(raw_text, organization, author_user_id):
    if not raw_text or not organization:
        return []

    import re

    mention_candidates = {m.lower() for m in re.findall(r'@([A-Za-z0-9_.-]{3,150})', raw_text)}
    if not mention_candidates:
        return []

    memberships = (
        OrganizationMembership.objects
        .filter(organization=organization, is_active=True)
        .select_related('user')
    )
    valid_users = []
    seen_user_ids = set()
    for membership in memberships:
        username = (membership.user.username or '').lower()
        if username in mention_candidates and membership.user_id != author_user_id and membership.user_id not in seen_user_ids:
            valid_users.append(membership.user)
            seen_user_ids.add(membership.user_id)
    return valid_users


def _build_contract_ai_response(contract, prompt):
    today = timezone.localdate()
    normalized_prompt = (prompt or '').strip().lower()

    risks = []
    if contract.risk_level in [Contract.RiskLevel.HIGH, Contract.RiskLevel.CRITICAL]:
        risks.append(f'Risk level is {contract.get_risk_level_display()}; prioritize legal review.')
    if contract.data_transfer_flag and not contract.dpa_attached:
        risks.append('Cross-border data transfer is enabled but no DPA is attached.')
    if contract.data_transfer_flag and not contract.scc_attached:
        risks.append('Cross-border transfer is enabled but SCCs are not marked as attached.')

    timeline = []
    if contract.end_date:
        days_to_end = (contract.end_date - today).days
        timeline.append(f'End date is in {days_to_end} day(s) on {contract.end_date.isoformat()}.')
    if contract.renewal_date:
        days_to_renewal = (contract.renewal_date - today).days
        timeline.append(f'Renewal date is in {days_to_renewal} day(s) on {contract.renewal_date.isoformat()}.')
    if contract.notice_period_days and contract.end_date:
        timeline.append(f'Notice period is {contract.notice_period_days} day(s).')

    recommendations = [
        'Verify business owner and legal owner are assigned for renewal decisions.',
        'Confirm required documents and amendment history are attached before approval.',
    ]
    if contract.auto_renew:
        recommendations.append('Auto-renew is enabled; set a cancellation checkpoint before notice deadline.')
    if 'renew' in normalized_prompt or 'expiry' in normalized_prompt or 'expire' in normalized_prompt:
        recommendations.append('Generate a renewal decision memo and circulate it to stakeholders now.')
    if 'risk' in normalized_prompt:
        recommendations.append('Run a clause-by-clause risk check and capture findings in negotiation notes.')

    citations = [
        {'field': 'status', 'value': contract.status},
        {'field': 'contract_type', 'value': contract.contract_type},
        {'field': 'risk_level', 'value': contract.risk_level},
        {'field': 'end_date', 'value': contract.end_date.isoformat() if contract.end_date else None},
        {'field': 'renewal_date', 'value': contract.renewal_date.isoformat() if contract.renewal_date else None},
    ]

    risk_findings = []
    if contract.risk_level in [Contract.RiskLevel.HIGH, Contract.RiskLevel.CRITICAL]:
        risk_findings.append(
            {
                'id': 'risk-level-alert',
                'severity': contract.risk_level,
                'finding': f'Contract risk level is {contract.get_risk_level_display()}.',
                'evidence_fields': ['risk_level'],
            }
        )
    if contract.data_transfer_flag and not contract.dpa_attached:
        risk_findings.append(
            {
                'id': 'dpa-missing',
                'severity': Contract.RiskLevel.HIGH,
                'finding': 'Cross-border data transfer is enabled but no DPA is attached.',
                'evidence_fields': ['contract_type'],
            }
        )
    if contract.data_transfer_flag and not contract.scc_attached:
        risk_findings.append(
            {
                'id': 'scc-missing',
                'severity': Contract.RiskLevel.HIGH,
                'finding': 'Cross-border transfer is enabled but SCCs are not marked as attached.',
                'evidence_fields': ['contract_type'],
            }
        )

    renewal_signals = []
    if contract.end_date:
        renewal_signals.append(
            {
                'id': 'end-date-signal',
                'detail': f'End date is {contract.end_date.isoformat()}.',
                'evidence_fields': ['end_date'],
                'confidence': 0.9,
            }
        )
    if contract.renewal_date:
        renewal_signals.append(
            {
                'id': 'renewal-date-signal',
                'detail': f'Renewal date is {contract.renewal_date.isoformat()}.',
                'evidence_fields': ['renewal_date'],
                'confidence': 0.9,
            }
        )

    clause_findings = []
    clause_candidates = ClauseTemplate.objects.filter(organization=contract.organization)
    if contract.contract_type:
        clause_candidates = clause_candidates.filter(
            Q(applicable_contract_types__icontains=contract.contract_type) | Q(applicable_contract_types__exact='')
        )
    clause_candidates = clause_candidates.order_by('-is_mandatory', '-is_approved', '-updated_at')[:12]

    for clause in clause_candidates:
        score = 0.2
        evidence_fields = []
        applicable_types = {item.strip().upper() for item in (clause.applicable_contract_types or '').split(',') if item.strip()}
        if not applicable_types or contract.contract_type in applicable_types:
            score += 0.45
            evidence_fields.append('contract_type')
        clause_scope = (clause.jurisdiction_scope or '').upper()
        contract_jurisdiction = (contract.jurisdiction or '').upper()
        if clause_scope in {'GLOBAL', ''}:
            score += 0.2
        elif clause_scope and clause_scope in contract_jurisdiction:
            score += 0.25
            evidence_fields.append('jurisdiction')
        if clause.is_mandatory:
            score += 0.1

        confidence = min(0.95, round(score, 2))
        if confidence >= 0.55:
            clause_findings.append(
                {
                    'clause_id': clause.id,
                    'title': clause.title,
                    'is_mandatory': clause.is_mandatory,
                    'jurisdiction_scope': clause.jurisdiction_scope,
                    'confidence': confidence,
                    'evidence_fields': sorted(set(evidence_fields)),
                }
            )

    clause_findings = clause_findings[:5]

    return {
        'summary': {
            'title': contract.title,
            'status': contract.get_status_display(),
            'contract_type': contract.get_contract_type_display(),
            'lifecycle_stage': contract.lifecycle_stage,
            'counterparty': contract.counterparty,
        },
        'timeline': timeline,
        'risks': risks,
        'recommendations': recommendations,
        'citations': citations,
        'extraction': {
            'schema_version': '1.0',
            'risk_findings': risk_findings,
            'renewal_signals': renewal_signals,
            'clause_findings': clause_findings,
            'recommended_actions': recommendations,
        },
        'output_policy': {
            'grounded_to_contract_fields': True,
            'external_data_used': False,
        },
        'mode': 'internal-rules-engine',
    }
