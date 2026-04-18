from django.core.management.base import BaseCommand

from contracts.services.document_ocr import process_pending_document_ocr_reviews


class Command(BaseCommand):
    help = 'Process pending OCR review jobs for uploaded documents.'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=50)

    def handle(self, *args, **options):
        processed = process_pending_document_ocr_reviews(limit=max(1, options['limit']))
        self.stdout.write(self.style.SUCCESS(f'Processed {processed} OCR review(s).'))
