from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from contracts.models import BackgroundJob
from contracts.services.background_jobs import process_background_job


class Command(BaseCommand):
    help = 'Process queued background jobs.'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=50)

    def handle(self, *args, **options):
        limit = max(1, options['limit'])
        processed = 0
        failures = 0
        jobs = (
            BackgroundJob.objects
            .filter(status=BackgroundJob.Status.PENDING)
            .filter(Q(scheduled_at__isnull=True) | Q(scheduled_at__lte=timezone.now()))
            .order_by('scheduled_at', 'created_at')[:limit]
        )
        for job in jobs:
            try:
                process_background_job(job)
            except Exception:
                failures += 1
            processed += 1
        self.stdout.write(self.style.SUCCESS(f'Processed {processed} background job(s). failures={failures}'))
