from django.core.management.base import BaseCommand
from django.conf import settings
from grounds.models import Ground
import os, shutil


def normalize(s):
    return ''.join(ch for ch in s.lower() if ch.isalnum())


class Command(BaseCommand):
    help = 'Sync images from project groundsimages/ into static/images/grounds and set Ground.image paths'

    def add_arguments(self, parser):
        parser.add_argument('--source', help='Source images directory (default: <BASE_DIR>/groundsimages)', default=None)
        parser.add_argument('--dest', help='Destination static directory (default: static/images/grounds)', default=None)
        parser.add_argument('--dry-run', action='store_true', help='Show actions without copying')

    def handle(self, *args, **options):
        base = settings.BASE_DIR
        src = options['source'] or os.path.join(base, 'groundsimages')
        dest_root = options['dest'] or os.path.join(base, 'static', 'images', 'grounds')
        dry = options['dry_run']

        if not os.path.isdir(src):
            self.stdout.write(self.style.ERROR(f'Source folder not found: {src}'))
            return

        os.makedirs(dest_root, exist_ok=True)

        files = [f for f in os.listdir(src) if os.path.isfile(os.path.join(src, f))]
        if not files:
            self.stdout.write(self.style.WARNING('No files found in source folder.'))
            return

        # Build quick lookup by normalized filename
        lookup = {}
        for f in files:
            key = normalize(f)
            lookup[key] = f

        updated = 0
        for ground in Ground.objects.all():
            norm = normalize(ground.name)
            # Try exact filename match first
            match = None
            if norm in lookup:
                match = lookup[norm]
            else:
                # Try substring match
                for key, fname in lookup.items():
                    if norm in key:
                        match = fname
                        break

            if match:
                src_path = os.path.join(src, match)
                safe_name = f"{ground.id}_{match}"
                dest_path = os.path.join(dest_root, safe_name)
                static_url = f"/static/images/grounds/{safe_name}"

                if dry:
                    self.stdout.write(f"Would copy {src_path} -> {dest_path} and set ground.image={static_url} for ground {ground.name}")
                    updated += 1
                    continue

                try:
                    shutil.copy2(src_path, dest_path)
                    ground.image = static_url
                    ground.save(update_fields=['image'])
                    self.stdout.write(self.style.SUCCESS(f'Updated image for ground {ground.name} -> {static_url}'))
                    updated += 1
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f'Failed for {ground.name}: {e}'))
            else:
                self.stdout.write(self.style.NOTICE(f'No image match for ground {ground.name}'))

        self.stdout.write(self.style.SUCCESS(f'Done. {updated} grounds updated.'))
