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
python manage.py collectstatic --noinput

echo "Starting ASGI server..."
exec daphne -b 0.0.0.0 -p 10000 config.asgi:application
