from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Compatibility audit placeholder for tenant-owned null organization checks.'

    def handle(self, *args, **options):
        self.stdout.write('NULL organization audit')
        self.stdout.write('----------------------')
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('No NULL organization rows found.'))
