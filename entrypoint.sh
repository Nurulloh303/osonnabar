#!/bin/sh
set -e

echo "→ Ma'lumotlar bazasini kutmoqda..."
python - <<'PY'
import os, time, sys
from urllib.parse import urlparse

url = os.environ.get("DATABASE_URL", "")
if url.startswith("postgres"):
    import socket
    p = urlparse(url)
    host, port = p.hostname, p.port or 5432
    for _ in range(60):
        try:
            socket.create_connection((host, port), timeout=2).close()
            print(f"  ✓ {host}:{port} tayyor")
            break
        except OSError:
            time.sleep(1)
    else:
        print("  ✗ Baza javob bermadi", file=sys.stderr)
        sys.exit(1)
PY

echo "→ Migratsiyalar..."
python manage.py migrate --noinput

echo "→ Statik fayllar..."
python manage.py collectstatic --noinput --clear >/dev/null

# Birinchi deployda super admin yaratish uchun. Akkaunt allaqachon bo'lsa —
# hech narsa qilinmaydi, ya'ni har restartda parol qayta yozilmaydi.
if [ -n "$DJANGO_SUPERUSER_PHONE" ] && [ -n "$DJANGO_SUPERUSER_PASSWORD" ]; then
  echo "→ Super admin tekshirilmoqda..."
  python - <<'PY'
import os

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()
from django.contrib.auth import get_user_model  # noqa: E402

User = get_user_model()
phone = os.environ["DJANGO_SUPERUSER_PHONE"]

if User.objects.filter(phone=phone).exists():
    print(f"  · {phone} allaqachon mavjud, o'zgartirilmadi")
else:
    User.objects.create_superuser(
        phone=phone,
        password=os.environ["DJANGO_SUPERUSER_PASSWORD"],
        full_name=os.environ.get("DJANGO_SUPERUSER_NAME", "Super Admin"),
    )
    print(f"  ✓ {phone} yaratildi")
PY
fi

if [ "$SEED_DEMO_DATA" = "1" ]; then
  echo "→ Demo ma'lumotlar..."
  python manage.py seed_demo
fi

exec "$@"
