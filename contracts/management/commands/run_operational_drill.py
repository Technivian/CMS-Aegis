from django.core.cache import cache
from django.core.management import BaseCommand, call_command
from django.utils import timezone


class Command(BaseCommand):
    help = 'Run an operational drill across reminders, OCR, and alert evaluation.'

    def handle(self, *args, **options):
        self.stdout.write('Queueing background jobs...')
        call_command('queue_background_jobs')

        self.stdout.write('Processing background jobs...')
        call_command('process_background_jobs', limit=100)

        self.stdout.write('Evaluating observability alerts...')
        call_command('evaluate_observability_alerts')

        summary = 'Queued reminder/OCR work, processed pending jobs, and evaluated alert policy.'
        cache.set('operations_drill.last_run_iso', timezone.now().isoformat(), timeout=None)
        cache.set('operations_drill.last_summary', summary, timeout=None)
        self.stdout.write(self.style.SUCCESS(summary))
