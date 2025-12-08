#!/usr/bin/env bash
set -euo pipefail

python --version

echo "Applying database migrations..."
python manage.py migrate --noinput

# Optionally create a superuser on first deploy if env vars are provided
if [[ -n "${DJANGO_SUPERUSER_USERNAME:-}" && -n "${DJANGO_SUPERUSER_PASSWORD:-}" ]]; then
  echo "Ensuring superuser ${DJANGO_SUPERUSER_USERNAME} exists..."
  python - <<'PY'
import os, django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()
from django.contrib.auth import get_user_model
User = get_user_model()
u = os.environ["DJANGO_SUPERUSER_USERNAME"]
p = os.environ["DJANGO_SUPERUSER_PASSWORD"]
e = os.environ.get("DJANGO_SUPERUSER_EMAIL", "")
if not User.objects.filter(username=u).exists():
    User.objects.create_superuser(username=u, password=p, email=e)
    print(f"Created superuser {u}")
else:
    print(f"Superuser {u} already exists")
PY
else
  echo "Skipping superuser creation; env vars not set."
fi

echo "Collecting static files..."
# Print STATIC_ROOT / MEDIA_ROOT from Django settings to help debugging where files live at runtime
echo "STATIC_ROOT / MEDIA_ROOT (runtime):"
python - <<'PY'
import os, django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()
from django.conf import settings
print('DEBUG=' + str(settings.DEBUG))
print('STATIC_ROOT=' + str(settings.STATIC_ROOT))
print('MEDIA_ROOT=' + str(settings.MEDIA_ROOT))
PY
# Ensure any existing media files checked into the repo are available under static/
# so WhiteNoise can serve them on platforms like Render where media uploads are ephemeral.
if [ -d "media" ]; then
  # If using S3/object storage for media, skip copying local media into static/
  if [ -n "${AWS_STORAGE_BUCKET_NAME:-}" ] || [ -n "${S3_BUCKET_NAME:-}" ]; then
    echo "S3 bucket configured (AWS_STORAGE_BUCKET_NAME or S3_BUCKET_NAME set). Skipping copying local media into static/"
  else
    mkdir -p static/media
    # copy media contents into static/media (ignore errors if empty)
    # Use a safer copy form that works whether media contains files or directories
    cp -a media/. static/media/ || true
  fi
fi

echo "Files copied into static/media (top-level):"
ls -la static/media || true

echo "Collecting static files..."
python manage.py collectstatic --noinput

echo "Files present under static/media (post-collect):"
ls -la static/media || true

# Ensure static/media exists and is writable (for serving uploads in production)
mkdir -p static/media
chmod -R 755 static/media || true

echo "Starting ASGI server..."
exec daphne -b 0.0.0.0 -p 10000 config.asgi:application
