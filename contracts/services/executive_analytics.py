from __future__ import annotations

from datetime import date, timedelta

from django.db.models import Avg, Count, DurationField, ExpressionWrapper, F
from django.db.models.functions import TruncMonth
from django.utils import timezone

from contracts.models import Contract, ExecutiveDashboardPreset


def build_executive_cycle_time_snapshot(organization, window_days: int = 180) -> dict:
    window_days = max(1, int(window_days))
    cycle_stats = (
        Contract.objects.filter(
            organization=organization,
            approved_at__isnull=False,
            created_at__gte=timezone.now() - timedelta(days=window_days),
        )
        .annotate(cycle_duration=ExpressionWrapper(F('approved_at') - F('created_at'), output_field=DurationField()))
        .aggregate(avg_cycle=Avg('cycle_duration'), sample_size=Count('id'))
    )
    avg_cycle_duration = cycle_stats.get('avg_cycle')
    avg_cycle_days = round(avg_cycle_duration.total_seconds() / 86400, 2) if avg_cycle_duration else None
    return {
        'window_days': window_days,
        'sample_size': cycle_stats.get('sample_size') or 0,
        'average_days': avg_cycle_days,
    }


def build_executive_bottlenecks(organization, limit: int = 5) -> list[dict]:
    rows = (
        Contract.objects.filter(organization=organization)
        .exclude(lifecycle_stage='ARCHIVED')
        .values('lifecycle_stage')
        .annotate(count=Count('id'))
        .order_by('-count', 'lifecycle_stage')[: max(1, int(limit))]
    )
    return [{'stage': row['lifecycle_stage'], 'count': row['count']} for row in rows]


def build_executive_risk_trend(organization, months: int = 6) -> list[dict]:
    months = max(1, int(months))
    since = timezone.now() - timedelta(days=31 * months)
    rows = (
        Contract.objects.filter(
            organization=organization,
            created_at__gte=since,
            risk_level__in=[Contract.RiskLevel.HIGH, Contract.RiskLevel.CRITICAL],
        )
        .annotate(month=TruncMonth('created_at'))
        .values('month')
        .annotate(total=Count('id'))
        .order_by('month')
    )
    trend_map = {
        row['month'].date().isoformat(): row['total']
        for row in rows
        if row.get('month')
    }

    today = date.today().replace(day=1)

    def _month_shift(first_of_month: date, delta: int) -> date:
        year = first_of_month.year
        month = first_of_month.month + delta
        while month <= 0:
            month += 12
            year -= 1
        while month > 12:
            month -= 12
            year += 1
        return date(year, month, 1)

    points = []
    for i in range(months - 1, -1, -1):
        bucket = _month_shift(today, -i)
        bucket_label = bucket.isoformat()
        points.append({'month': bucket_label, 'high_or_critical_count': trend_map.get(bucket_label, 0)})
    return points


def build_executive_saved_dashboards(organization, limit: int = 20) -> list[dict]:
    presets = (
        ExecutiveDashboardPreset.objects.filter(organization=organization, is_shared=True)
        .select_related('created_by')
        .order_by('name')[: max(1, int(limit))]
    )
    return [
        {
            'id': preset.id,
            'name': preset.name,
            'filters': preset.filters,
            'layout': preset.layout,
            'created_by': preset.created_by.username if preset.created_by else None,
            'created_at': preset.created_at.isoformat() if preset.created_at else None,
            'updated_at': preset.updated_at.isoformat() if preset.updated_at else None,
        }
        for preset in presets
    ]


def build_executive_analytics_snapshot(organization) -> dict:
    return {
        'organization': {'id': organization.id, 'slug': organization.slug},
        'cycle_time': build_executive_cycle_time_snapshot(organization),
        'bottlenecks': build_executive_bottlenecks(organization),
        'risk_trend': build_executive_risk_trend(organization),
        'saved_dashboards': build_executive_saved_dashboards(organization),
    }
