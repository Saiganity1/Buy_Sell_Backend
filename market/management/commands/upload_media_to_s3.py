from django.core.management.base import BaseCommand
from django.core.files import File
from django.conf import settings
from django.core.files.storage import default_storage
import os


class Command(BaseCommand):
    help = (
        "Upload files under MEDIA_ROOT into the configured DEFAULT_FILE_STORAGE. "
        "Useful for migrating local media files into S3 or another object store."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true', dest='dry_run', help='Show files that would be uploaded but do not upload.'
        )
        parser.add_argument(
            '--overwrite', action='store_true', dest='overwrite', help='Overwrite files already present in the storage.'
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        overwrite = options['overwrite']

        media_root = getattr(settings, 'MEDIA_ROOT', None)
        if not media_root:
            self.stderr.write('MEDIA_ROOT is not configured.')
            return

        self.stdout.write(f'MEDIA_ROOT = {media_root}')

        # If default_storage is local FileSystemStorage, warn the user
        storage_class = default_storage.__class__.__name__
        self.stdout.write(f'Using storage backend: {storage_class}')

        uploaded = 0
        skipped = 0

        if not os.path.isdir(media_root):
            self.stderr.write('No media directory found to upload.')
            return

        for root, dirs, files in os.walk(media_root):
            for fname in files:
                full_path = os.path.join(root, fname)
                # relative path within MEDIA_ROOT (use forward slashes for storage path)
                rel_path = os.path.relpath(full_path, media_root).replace('\\', '/')

                # If storage already has the file and not overwriting, skip
                if default_storage.exists(rel_path) and not overwrite:
                    skipped += 1
                    self.stdout.write(f'SKIP (exists): {rel_path}')
                    continue

                if dry_run:
                    self.stdout.write(f'WOULD UPLOAD: {rel_path}')
                    uploaded += 1
                    continue

                # Upload file
                with open(full_path, 'rb') as f:
                    django_file = File(f)
                    try:
                        saved_name = default_storage.save(rel_path, django_file)
                    except Exception as e:
                        self.stderr.write(f'ERROR uploading {rel_path}: {e}')
                        continue

                self.stdout.write(f'UPLOADED: {rel_path} -> {saved_name}')
                uploaded += 1

        self.stdout.write('Done.')
        self.stdout.write(f'Uploaded: {uploaded}, Skipped: {skipped}')
