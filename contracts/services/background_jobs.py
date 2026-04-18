from __future__ import annotations

from datetime import timedelta

from django.core.management import call_command
from django.db.models import Q
from django.utils import timezone

from contracts.models import BackgroundJob


def queue_background_job(job_type: str, organization=None, payload=None, created_by=None, scheduled_at=None):
    if organization is not None and BackgroundJob.objects.filter(
        organization=organization,
        job_type=job_type,
        status=BackgroundJob.Status.PENDING,
        scheduled_at__gte=timezone.now() - timedelta(minutes=15),
    ).exists():
        return BackgroundJob.objects.filter(
            organization=organization,
            job_type=job_type,
            status=BackgroundJob.Status.PENDING,
        ).order_by('-scheduled_at', '-created_at').first()
    return BackgroundJob.objects.create(
        organization=organization,
        job_type=job_type,
        payload=payload or {},
        created_by=created_by,
        scheduled_at=scheduled_at or timezone.now(),
    )


def process_background_job(job: BackgroundJob):
    job.status = BackgroundJob.Status.RUNNING
    job.started_at = timezone.now()
    job.attempt_count = int(job.attempt_count or 0) + 1
    job.save(update_fields=['status', 'started_at', 'attempt_count'])
    try:
        if job.job_type == 'send_contract_reminders':
            call_command('send_contract_reminders')
            job.result = {'processed': True}
        elif job.job_type == 'process_document_ocr_reviews':
            call_command('process_document_ocr_reviews')
            job.result = {'processed': True}
        elif job.job_type == 'sync_salesforce_contracts':
            if not job.organization:
                raise RuntimeError('sync_salesforce_contracts requires organization context')
            call_command(
                'sync_salesforce_contracts',
                organization_slug=job.organization.slug,
                limit=int((job.payload or {}).get('limit', 200) or 200),
                dry_run=bool((job.payload or {}).get('dry_run', False)),
            )
            job.result = {'processed': True}
        else:
            job.result = {'processed': False, 'reason': 'unknown_job_type'}
        job.status = BackgroundJob.Status.COMPLETED
        job.completed_at = timezone.now()
        job.save(update_fields=['status', 'result', 'completed_at'])
    except Exception as exc:
        max_attempts = max(1, int(job.max_attempts or 3))
        if int(job.attempt_count or 0) < max_attempts:
            delay_minutes = min(60, 5 * (2 ** (int(job.attempt_count or 0) - 1)))
            job.status = BackgroundJob.Status.PENDING
            job.error_message = str(exc)
            job.scheduled_at = timezone.now() + timedelta(minutes=delay_minutes)
            job.save(update_fields=['status', 'error_message', 'scheduled_at'])
        else:
            job.status = BackgroundJob.Status.FAILED
            job.error_message = str(exc)
            job.dead_lettered_at = timezone.now()
            job.completed_at = timezone.now()
            job.save(update_fields=['status', 'error_message', 'dead_lettered_at', 'completed_at'])
        raise


def process_pending_background_jobs(limit=50):
    processed = 0
    pending_jobs = (
        BackgroundJob.objects
        .filter(status=BackgroundJob.Status.PENDING)
        .filter(Q(scheduled_at__isnull=True) | Q(scheduled_at__lte=timezone.now()))
        .order_by('scheduled_at', 'created_at')[:limit]
    )
    for job in pending_jobs:
        process_background_job(job)
        processed += 1
    return processed
