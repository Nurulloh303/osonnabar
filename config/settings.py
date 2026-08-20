"""osonNavbat backend sozlamalari."""

from datetime import timedelta
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env()
environ.Env.read_env(BASE_DIR / ".env")

# ── Asosiy ───────────────────────────────────────────────────────────────
INSECURE_DEV_KEY = "insecure-dev-key-do-not-use-in-prod"

SECRET_KEY = env("DJANGO_SECRET_KEY", default=INSECURE_DEV_KEY)
DEBUG = env.bool("DJANGO_DEBUG", default=False)
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])
# Docker HEALTHCHECK konteyner ichidan `127.0.0.1` orqali uradi — tashqi domenni
# qanday sozlasak ham bu doim ruxsat etilgan bo'lishi kerak. Xavfsiz: `127.0.0.1`
# faqat konteynerning o'z ichidan yetib boriladi, tashqaridan emas (`expose`,
# `ports` emas).
for _loopback_host in ("127.0.0.1", "localhost"):
    if _loopback_host not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append(_loopback_host)

#: `True` bo'lsa — server internetga chiqarilgan rejimda ishlaydi.
IS_PRODUCTION = not DEBUG

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # 3rd party
    "rest_framework",
    "corsheaders",
    "django_filters",
    "drf_spectacular",
    # local
    "apps.common",
    "apps.accounts",
    "apps.salons",
    "apps.bookings",
    "apps.reviews",
    "apps.dashboard",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# ── Baza ─────────────────────────────────────────────────────────────────
DATABASES = {
    "default": env.db_url(
        "DATABASE_URL",
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
    )
}
DATABASES["default"]["ATOMIC_REQUESTS"] = False
DATABASES["default"]["CONN_MAX_AGE"] = env.int("DB_CONN_MAX_AGE", default=60)

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
]

# ── Til / vaqt ───────────────────────────────────────────────────────────
LANGUAGE_CODE = "uz"
TIME_ZONE = env("DJANGO_TIME_ZONE", default="Asia/Tashkent")
USE_I18N = True
USE_TZ = True

# ── Statik / media ───────────────────────────────────────────────────────
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

#: Media (avatar, muqova rasmi) ni Django o'zi bersinmi?
#: Nginx `/media/` ni to'g'ridan-to'g'ri bersa — buni `False` qiling, tezroq bo'ladi.
#: `local` saqlashda default `True`, aks holda prodda barcha rasmlar 404 bo'ladi.
SERVE_MEDIA = env.bool("SERVE_MEDIA", default=True)

STORAGE_BACKEND = env("STORAGE_BACKEND", default="local")
if STORAGE_BACKEND == "s3":
    AWS_ACCESS_KEY_ID = env("AWS_ACCESS_KEY_ID", default="")
    AWS_SECRET_ACCESS_KEY = env("AWS_SECRET_ACCESS_KEY", default="")
    AWS_STORAGE_BUCKET_NAME = env("AWS_STORAGE_BUCKET_NAME", default="")
    AWS_S3_ENDPOINT_URL = env("AWS_S3_ENDPOINT_URL", default=None) or None
    AWS_S3_REGION_NAME = env("AWS_S3_REGION_NAME", default="us-east-1")
    AWS_S3_CUSTOM_DOMAIN = env("AWS_S3_CUSTOM_DOMAIN", default=None) or None
    AWS_QUERYSTRING_AUTH = False
    AWS_S3_FILE_OVERWRITE = False
    AWS_DEFAULT_ACL = None
    default_storage = {"BACKEND": "storages.backends.s3.S3Storage"}
else:
    default_storage = {"BACKEND": "django.core.files.storage.FileSystemStorage"}

STORAGES = {
    "default": default_storage,
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

# ── Cache ────────────────────────────────────────────────────────────────
REDIS_URL = env("REDIS_URL", default="")
if REDIS_URL:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": REDIS_URL,
        }
    }
else:
    CACHES = {
        "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}
    }
    if IS_PRODUCTION:
        # LocMemCache har bir gunicorn worker'ida alohida yashaydi. Throttle
        # hisoblagichlari ham shu yerda turadi — ya'ni 3 worker'da OTP limiti
        # amalda 3 barobar bo'lib ketadi va restartda nolga tushadi.
        import warnings

        warnings.warn(
            "REDIS_URL bo'sh: throttling har bir worker'da alohida hisoblanadi va "
            "OTP limitlari kuchsizlanadi. Prodda Redis ulang.",
            RuntimeWarning,
            stacklevel=2,
        )

# ── CORS / CSRF ──────────────────────────────────────────────────────────
# Frontend (qulaybron.uz) va API (api.qulaybron.uz) alohida originlarda turadi,
# shuning uchun brauzer har bir so'rovdan oldin CORS preflight yuboradi.
CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=["http://localhost:3000"])
#: Vercel/preview deploylar uchun: `^https://.*\.vercel\.app$` kabi shablonlar.
CORS_ALLOWED_ORIGIN_REGEXES = env.list("CORS_ALLOWED_ORIGIN_REGEXES", default=[])
CORS_ALLOW_CREDENTIALS = True  # httpOnly cookie'lar uchun majburiy
CORS_PREFLIGHT_MAX_AGE = 86400  # preflight javobini 24 soat cache'lash
#: Front paginatsiya/limit header'larini o'qiy olishi uchun.
CORS_EXPOSE_HEADERS = ["Content-Disposition", "Retry-After"]
#: `X-CSRFToken` django-cors-headers'ning standart ro'yxatida bor — qo'shimcha
#: header kerak bo'lsa shu yerga (CORS_ALLOW_HEADERS) qo'shiladi.

CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=["http://localhost:3000"])
FRONTEND_URL = env("FRONTEND_URL", default="http://localhost:3000")

CSRF_COOKIE_HTTPONLY = False  # front JS `csrftoken`ni o'qib, header'ga qo'yadi
CSRF_COOKIE_SAMESITE = env("AUTH_COOKIE_SAMESITE", default="Lax")
CSRF_COOKIE_SECURE = env.bool("AUTH_COOKIE_SECURE", default=IS_PRODUCTION)
CSRF_COOKIE_DOMAIN = env("AUTH_COOKIE_DOMAIN", default="") or None

# ── Prod xavfsizligi ─────────────────────────────────────────────────────
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = CSRF_COOKIE_SAMESITE
SESSION_COOKIE_SECURE = env.bool("AUTH_COOKIE_SECURE", default=IS_PRODUCTION)
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
X_FRAME_OPTIONS = "DENY"

if IS_PRODUCTION:
    # Nginx/Traefik orqasida turibmiz — HTTPS ni shu header orqali bilamiz.
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=True)
    # Healthcheck'ni HTTPS'ga yo'naltirmaymiz, aks holda LB uni "o'lik" deb biladi.
    SECURE_REDIRECT_EXEMPT = [r"^health/$"]
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

# ── Yuklanadigan fayllar uchun cheklovlar ────────────────────────────────
#: Avatar/muqova rasmi uchun maksimal hajm (bayt). Undan kattasi 400 bilan qaytadi.
MAX_UPLOAD_SIZE = env.int("MAX_UPLOAD_SIZE", default=5 * 1024 * 1024)
DATA_UPLOAD_MAX_MEMORY_SIZE = MAX_UPLOAD_SIZE + 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = DATA_UPLOAD_MAX_MEMORY_SIZE
DATA_UPLOAD_MAX_NUMBER_FIELDS = 200

# ── Prodda xavfli konfiguratsiyani ishga tushirmaymiz ────────────────────
# Bular "ogohlantirish" emas — server ko'tarilmaydi. Sababi: har biri
# to'g'ridan-to'g'ri akkaunt o'g'irlashga olib keladigan teshik.
if IS_PRODUCTION:
    _fatal = []
    if SECRET_KEY == INSECURE_DEV_KEY or len(SECRET_KEY) < 50:
        _fatal.append(
            "DJANGO_SECRET_KEY zaif yoki standart qiymatda. U JWT tokenlarni ham "
            "imzolaydi — bilgan odam istalgan foydalanuvchi (super admin ham) "
            "nomidan token yasay oladi. Yangisini quyidagicha yarating:\n"
            "  python -c \"import secrets; print(secrets.token_urlsafe(64))\""
        )
    if "*" in ALLOWED_HOSTS:
        _fatal.append("DJANGO_ALLOWED_HOSTS da '*' bo'lmasligi kerak — aniq domenlarni yozing.")
    if not CORS_ALLOWED_ORIGINS and not CORS_ALLOWED_ORIGIN_REGEXES:
        _fatal.append("CORS_ALLOWED_ORIGINS bo'sh — frontend API'ga ulana olmaydi.")
    if not CSRF_COOKIE_SECURE:
        # Odatiy xato: lokal `.env` ni serverga ko'chirib, faqat DEBUG o'chiriladi.
        # Natijada auth va CSRF cookie'lari `Secure` bayrog'isiz ketadi va ochiq
        # Wi-Fi'da sessiyani o'g'irlash mumkin bo'lib qoladi.
        _fatal.append(
            "AUTH_COOKIE_SECURE=True bo'lishi kerak — aks holda tokenlar shifrlanmagan "
            "ulanish orqali ham yuboriladi. Lokal `.env` ni ko'chirgan bo'lsangiz, "
            "`.env.production.example` dan qayta boshlang."
        )
    if _fatal:
        raise RuntimeError(
            "Production konfiguratsiyasida xatolik:\n  - " + "\n  - ".join(_fatal)
        )

# ── Auth cookie ──────────────────────────────────────────────────────────
AUTH_COOKIE_ACCESS = "on_access"
AUTH_COOKIE_REFRESH = "on_refresh"
AUTH_COOKIE_SECURE = env.bool("AUTH_COOKIE_SECURE", default=IS_PRODUCTION)
AUTH_COOKIE_SAMESITE = env("AUTH_COOKIE_SAMESITE", default="Lax")
AUTH_COOKIE_DOMAIN = env("AUTH_COOKIE_DOMAIN", default="") or None
AUTH_COOKIE_PATH = "/"

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=env.int("ACCESS_TOKEN_LIFETIME_MINUTES", default=30)),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=env.int("REFRESH_TOKEN_LIFETIME_DAYS", default=30)),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": False,
    "UPDATE_LAST_LOGIN": True,
    "ALGORITHM": "HS256",
    "SIGNING_KEY": SECRET_KEY,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
    "TOKEN_TYPE_CLAIM": "token_type",
}

# ── DRF ──────────────────────────────────────────────────────────────────
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "apps.accounts.authentication.CookieJWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_PAGINATION_CLASS": "apps.common.pagination.DefaultPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_FILTER_BACKENDS": (
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ),
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "apps.common.exceptions.api_exception_handler",
    "DEFAULT_THROTTLE_CLASSES": (
        "rest_framework.throttling.ScopedRateThrottle",
        # Scoped throttle faqat `throttle_scope` qo'yilgan view'larda ishlaydi;
        # qolgan barcha endpoint'lar shu ikkitasi bilan yopiladi.
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ),
    "DEFAULT_THROTTLE_RATES": {
        "anon": env("THROTTLE_ANON", default="120/min"),
        "user": env("THROTTLE_USER", default="300/min"),
        "otp_request": env("THROTTLE_OTP_REQUEST", default="5/hour"),
        "otp_verify": env("THROTTLE_OTP_VERIFY", default="15/hour"),
        "booking_create": env("THROTTLE_BOOKING_CREATE", default="30/hour"),
    },
    # ⚠️ Nginx orqasida MAJBURIY. Bo'sh qolsa DRF butun `X-Forwarded-For`
    # zanjirini kalit qilib oladi — hujumchi header'ni o'zi yozib, har safar
    # yangi "IP" ko'rsatib limitni cheksiz aylanib o'tadi (SMS bombardimon).
    # 1 = bizning oldimizda bitta ishonchli proxy bor.
    "NUM_PROXIES": env.int("NUM_PROXIES", default=1 if IS_PRODUCTION else 0),
    "DATETIME_FORMAT": "%Y-%m-%dT%H:%M:%S%z",
    "TIME_FORMAT": "%H:%M",
}

#: `/api/docs/`, `/api/redoc/`, `/api/schema/` umuman chiqarilsinmi.
ENABLE_API_DOCS = env.bool("ENABLE_API_DOCS", default=True)

#: Django admin paneli manzili. Prodda uni `/admin/` da qoldirmang —
#: botlar aynan shu manzilga parol tanlashga uriniladi.
DJANGO_ADMIN_URL = env("DJANGO_ADMIN_URL", default="admin/").strip("/") + "/"

SPECTACULAR_SETTINGS = {
    "TITLE": "osonNavbat API",
    "DESCRIPTION": (
        "Sartaroshxona va go'zallik salonlari uchun onlayn navbat platformasi.\n\n"
        "**Autentifikatsiya:** JWT tokenlar `httpOnly` cookie'da saqlanadi "
        "(`on_access` / `on_refresh`). Har bir o'zgartiruvchi so'rovda "
        "`X-CSRFToken` header'i talab qilinadi — tokenni `GET /api/v1/auth/csrf/` "
        "orqali oling. Swagger'dan test qilish uchun `Authorization: Bearer <token>` "
        "ham qo'llab-quvvatlanadi."
    ),
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    "SCHEMA_PATH_PREFIX": "/api/v1",
    # Prodda /api/docs/ hammaga ochiq turishi — super admin endpoint'lari
    # ro'yxatini hujumchiga tayyor holda berish demak.
    "SERVE_PERMISSIONS": ["rest_framework.permissions.AllowAny"]
    if DEBUG
    else ["rest_framework.permissions.IsAdminUser"],
    "TAGS": [
        {"name": "auth", "description": "Ro'yxatdan o'tish, OTP, Google, sessiya"},
        {"name": "salons", "description": "Salonlar"},
        {"name": "barbers", "description": "Ustalar, jadval, bo'sh vaqtlar"},
        {"name": "bookings", "description": "Navbatlar (bronlar)"},
        {"name": "reviews", "description": "Sharhlar va reyting"},
        {"name": "barber-panel", "description": "Usta paneli"},
        {"name": "admin-panel", "description": "Super admin paneli"},
    ],
}

# ── SMS / OTP ────────────────────────────────────────────────────────────
SMS_BACKENDS = {
    "console": "apps.accounts.sms.backends.ConsoleSMSBackend",
    "eskiz": "apps.accounts.sms.backends.EskizSMSBackend",
    "playmobile": "apps.accounts.sms.backends.PlaymobileSMSBackend",
}
SMS_BACKEND = env("SMS_BACKEND", default="console")

OTP_LENGTH = env.int("OTP_LENGTH", default=4)
OTP_TTL_SECONDS = env.int("OTP_TTL_SECONDS", default=120)
OTP_MAX_ATTEMPTS = env.int("OTP_MAX_ATTEMPTS", default=5)
OTP_RESEND_COOLDOWN_SECONDS = env.int("OTP_RESEND_COOLDOWN_SECONDS", default=60)
OTP_RETURN_IN_RESPONSE = env.bool("OTP_RETURN_IN_RESPONSE", default=False)
OTP_TEST_PHONES = env.list("OTP_TEST_PHONES", default=[])
OTP_DEBUG_CODE = env("OTP_DEBUG_CODE", default="0000")

if IS_PRODUCTION and OTP_TEST_PHONES:
    # Kod darajasida ham himoya bor (`PhoneOTP.generate_code` DEBUG'ni tekshiradi),
    # lekin bu sozlama prodda umuman turmasligi kerak — shuning uchun aniq xato.
    raise RuntimeError(
        "OTP_TEST_PHONES production'da bo'sh bo'lishi shart. Aks holda bu raqamlar "
        f"doimiy '{OTP_DEBUG_CODE}' kodi bilan kira olardi. `.env` dan olib tashlang."
    )

ESKIZ_EMAIL = env("ESKIZ_EMAIL", default="")
ESKIZ_PASSWORD = env("ESKIZ_PASSWORD", default="")
ESKIZ_FROM = env("ESKIZ_FROM", default="4546")
ESKIZ_BASE_URL = env("ESKIZ_BASE_URL", default="https://notify.eskiz.uz/api")

PLAYMOBILE_LOGIN = env("PLAYMOBILE_LOGIN", default="")
PLAYMOBILE_PASSWORD = env("PLAYMOBILE_PASSWORD", default="")
PLAYMOBILE_FROM = env("PLAYMOBILE_FROM", default="3700")
PLAYMOBILE_BASE_URL = env("PLAYMOBILE_BASE_URL", default="http://91.204.239.44/broker-api")

# ── Google OAuth ─────────────────────────────────────────────────────────
GOOGLE_CLIENT_ID = env("GOOGLE_CLIENT_ID", default="")

# ── Biznes qoidalari ─────────────────────────────────────────────────────
BOOKING_CANCEL_WINDOW_MINUTES = env.int("BOOKING_CANCEL_WINDOW_MINUTES", default=60)
BOOKING_MAX_DAYS_AHEAD = env.int("BOOKING_MAX_DAYS_AHEAD", default=30)
BOOKING_MAX_ACTIVE_PER_CLIENT = env.int("BOOKING_MAX_ACTIVE_PER_CLIENT", default=5)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"simple": {"format": "[{levelname}] {name}: {message}", "style": "{"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "simple"}},
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        "apps": {"handlers": ["console"], "level": "DEBUG" if DEBUG else "INFO", "propagate": False},
    },
}
