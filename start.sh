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
# Ensure any existing media files checked into the repo are available under static/
# so WhiteNoise can serve them on platforms like Render where media uploads are ephemeral.
if [ -d "media" ]; then
  mkdir -p static/media
  # copy media contents into static/media (ignore errors if empty)
  # Use a safer copy form that works whether media contains files or directories
  cp -a media/. static/media/ || true
fi

python manage.py collectstatic --noinput

# Ensure static/media exists and is writable (for serving uploads in production)
mkdir -p static/media
chmod -R 755 static/media || true

echo "Starting ASGI server..."
exec daphne -b 0.0.0.0 -p 10000 config.asgi:application
