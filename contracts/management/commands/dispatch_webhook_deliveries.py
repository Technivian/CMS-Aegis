from django.core.management.base import BaseCommand

from contracts.services.webhooks import dispatch_pending_webhook_deliveries


class Command(BaseCommand):
    help = 'Dispatch pending webhook deliveries with retry/dead-letter behavior.'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=100)

    def handle(self, *args, **options):
        processed = dispatch_pending_webhook_deliveries(limit=max(1, int(options['limit'])))
        self.stdout.write(self.style.SUCCESS(f'Dispatched {processed} webhook delivery item(s).'))
