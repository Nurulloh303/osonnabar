# osonNavbat — serverga joylash (qulaynavbat.uz)

Arxitektura:

```
  qulaynavbat.uz            api.qulaynavbat.uz
  (Next.js frontend)  ──▶  nginx :443  ──▶  gunicorn (api:8000)
                             │                   ├── postgres (ichki tarmoq)
                             ├── /media/         └── redis    (ichki tarmoq)
                             └── /static/
```

`qulaynavbat.uz` va `api.qulaynavbat.uz` bitta **site** (eTLD+1 bir xil) — shuning uchun
auth cookie'lar `SameSite=Lax` bilan ishlaydi va bu `SameSite=None` dan xavfsizroq.

Backend (bu papka) **faqat** `api.qulaynavbat.uz` da turadi. Frontend alohida joyda
(masalan Vercel) joylashtiriladi — bu qo'llanma ularni bir-biriga ulashni ko'rsatadi.

---

## 0. DigitalOcean Droplet yaratish

**Tavsiya etilgan konfiguratsiya:**

| Parametr | Qiymat | Izoh |
|---|---|---|
| Image | Ubuntu 24.04 (LTS) x64 | |
| Plan | Basic → Regular SSD | |
| O'lcham | **2 GB RAM / 1 vCPU (~$12/oy)** | Postgres + Redis + gunicorn (3 worker) + nginx shu tashda birga ishlaydi. 1 GB ($6/oy) juda tor — `docker compose up --build` paytida yoki bir nechta so'rov bir vaqtda kelganda xotira tugab qolishi (OOM) mumkin. |
| Region | Frankfurt (fra1) yoki Singapore (sgp1) | O'zbekistondan eng yaqin DO regionlari shular — ikkalasini ham `ping`lab, qaysi tezroq bo'lsa shuni tanlang. |
| Authentication | **SSH Key** (parol emas) | Yaratish oynasida "New SSH Key" — lokal mashinangizdagi `~/.ssh/id_ed25519.pub` ni joylashtiring. |
| Backups | Yoqing (ixtiyoriy, +20% narx) | Haftalik avtomatik zaxira — foydali, lekin keyinroq ham yoqish mumkin. |

Droplet yaratilgach, unga tegishli **IP manzilni** yozib qo'ying — keyingi barcha qadamlarda kerak bo'ladi.

## 1. Server boshlang'ich sozlash

SSH orqali kiring:

```bash
ssh root@<DROPLET_IP>
```

Docker o'rnatish (rasmiy skript):

```bash
curl -fsSL https://get.docker.com | sh
```

Firewall — faqat SSH, HTTP, HTTPS ochiq qolsin (baza/redis portlari **hech qachon**
tashqariga chiqmasligi kerak):

```bash
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable
```

## 2. Kodni serverga yetkazish

Bu loyihada hali git commit/remote yo'q. Ikki yo'l bor — birinchisini tavsiya qilaman
(kelajakda yangilash `git pull` bilan bir buyruqqa aylanadi):

**A) GitHub orqali (tavsiya etiladi)**

Lokal mashinada (bu papkada):

```bash
git add -A
git commit -m "osonNavbat backend"
```

GitHub'da bo'sh **private** repo yarating, so'ng:

```bash
git remote add origin git@github.com:<username>/osonnavbat.git
git push -u origin master
```

Serverda:

```bash
git clone git@github.com:<username>/osonnavbat.git /opt/osonnavbat
cd /opt/osonnavbat
```

*(Private repo bo'lsa, serverga deploy key qo'shish kerak bo'ladi — GitHub'da
repo → Settings → Deploy keys.)*

**B) To'g'ridan-to'g'ri nusxalash (tezroq, lekin yangilash qo'lda)**

Lokal mashinada, `.venv`, `.git`, `db.sqlite3` ni tashlab:

```bash
rsync -avz --exclude .venv --exclude .git --exclude db.sqlite3 --exclude __pycache__ ./ root@<DROPLET_IP>:/opt/osonnavbat/
```

Windows'da `rsync` bo'lmasa, `scp -r` yoki WinSCP bilan ham bo'ladi.

## 3. DNS

Domen registratoringizda (yoki DO DNS'ga qo'shgan bo'lsangiz — shu yerda):

| Yozuv | Turi | Qiymat |
|---|---|---|
| `api.qulaynavbat.uz` | A | `<DROPLET_IP>` |

Frontend qayerda tursa, `qulaynavbat.uz` shu yerga qarab qoladi (masalan Vercel'ning
o'ziga xos A/CNAME yozuvi) — buni backend bilan bog'liq emas, o'zgartirish shart emas.

Tarqalishini tekshirish (1 soatgacha vaqt olishi mumkin):

```bash
dig +short api.qulaynavbat.uz
```

## 4. Muhit fayli

Serverda, `/opt/osonnavbat` ichida:

```bash
cp .env.production.example .env
```

Yangi kalit yarating va `.env` ga qo'ying:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(64))"
```

`.env` da to'ldirilishi shart bo'lgan joylar:

- `DJANGO_SECRET_KEY` — yuqoridagi buyruq natijasi
- `POSTGRES_PASSWORD` va `DATABASE_URL` ichidagi parol (bir xil bo'lsin)
- `SMS_BACKEND` + provayder kaliti (`ESKIZ_*` yoki `PLAYMOBILE_*`) — `console` prodga yaramaydi
- `GOOGLE_CLIENT_ID`
- `DJANGO_ADMIN_URL` — `/admin/` da qoldirmang, masalan `boshqaruv-x7f2/`

Birinchi super adminni avtomatik yaratish uchun (ixtiyoriy, `entrypoint.sh` shuni o'qiydi):

```
DJANGO_SUPERUSER_PHONE=+998901112233
DJANGO_SUPERUSER_PASSWORD=<kuchli parol>
DJANGO_SUPERUSER_NAME=Super Admin
```

## 5. TLS sertifikat (birinchi marta)

nginx sertifikatsiz ko'tarilmaydi, shuning uchun avval sertifikat olinadi
(80-port shu payt bo'sh bo'lishi kerak — nginx konteyneri hali ishga tushmagan):

```bash
mkdir -p deploy/certbot/www deploy/certbot/conf
docker run --rm -p 80:80 \
  -v "$PWD/deploy/certbot/conf:/etc/letsencrypt" \
  -v "$PWD/deploy/certbot/www:/var/www/certbot" \
  certbot/certbot certonly --standalone \
  -d api.qulaynavbat.uz --agree-tos -m nurulloh166@gmail.com --no-eff-email
```

Keyinchalik `certbot` konteyneri uni har 12 soatda o'zi yangilab turadi.

## 6. Ishga tushirish

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

Loglar:

```bash
docker compose -f docker-compose.prod.yml logs -f api
```

## 7. Tekshirish

```bash
curl -s https://api.qulaynavbat.uz/health/
```

Kutilgan: `{"status": "ok", "service": "osonnavbat-api", "database": true}`

CORS to'g'ri ishlayotganini tekshirish (frontend nomidan preflight):

```bash
curl -si -X OPTIONS https://api.qulaynavbat.uz/api/v1/auth/otp/request/ -H "Origin: https://qulaynavbat.uz" -H "Access-Control-Request-Method: POST" -H "Access-Control-Request-Headers: content-type,x-csrftoken" | grep -i access-control
```

Kutilgan javob:

```
access-control-allow-origin: https://qulaynavbat.uz
access-control-allow-credentials: true
```

---

## Frontend tomonida nima qilish kerak

API base URL: `https://api.qulaynavbat.uz/api/v1`

1. **Muhit o'zgaruvchisi** — frontend hosting'ida (Vercel bo'lsa, project → Settings
   → Environment Variables):

   ```
   NEXT_PUBLIC_API_URL=https://api.qulaynavbat.uz/api/v1
   ```

2. **Har bir so'rovda `credentials: "include"`** — tokenlar `httpOnly` cookie'da,
   ularsiz brauzer cookie yubormaydi:

   ```js
   fetch(`${API}/salons/`, { credentials: "include" })
   ```

   Agar `axios` ishlatilsa: `axios.create({ baseURL: API, withCredentials: true })`.

3. **O'zgartiruvchi so'rovlarda (POST/PATCH/DELETE) CSRF token.**
   Ilova yuklanganda bir marta:

   ```js
   await fetch(`${API}/auth/csrf/`, { credentials: "include" });
   ```

   so'ng brauzerdagi `csrftoken` cookie'sini o'qib, uni `X-CSRFToken` header'iga
   qo'ying (bearer token bilan Swagger/mobil ishlatsangiz bu shart emas).

4. **Google Sign-In** ishlatilsa — Google Cloud Console → OAuth client →
   *Authorized JavaScript origins* ga qo'shing: `https://qulaynavbat.uz`

5. Frontend `qulaynavbat.uz` boshqa joyda (Vercel va h.k.) turibdimi, yoki uni ham
   shu DigitalOcean droplet'ga qo'yish kerakmi — agar ikkinchisi bo'lsa ayting,
   `docker-compose.prod.yml` ga frontend uchun alohida konteyner va nginx'ga
   apex domen (`qulaynavbat.uz`) uchun blok qo'shib beraman.

---

## Joylashdan oldingi ro'yxat

- [ ] `DJANGO_DEBUG=False`
- [ ] `DJANGO_SECRET_KEY` yangi va 50+ belgi *(bo'lmasa server ishga tushmaydi)*
- [ ] `OTP_TEST_PHONES` bo'sh *(bo'lmasa server ishga tushmaydi)*
- [ ] `AUTH_COOKIE_SECURE=True` *(bo'lmasa server ishga tushmaydi)*
- [ ] `OTP_RETURN_IN_RESPONSE=False`
- [ ] `SMS_BACKEND` — `console` emas
- [ ] `REDIS_URL` to'ldirilgan *(throttling shunga bog'liq)*
- [ ] `NUM_PROXIES=1` *(nginx orqasida)*
- [ ] `POSTGRES_PASSWORD` — standart emas
- [ ] `DJANGO_ADMIN_URL` — `/admin/` emas
- [ ] Droplet firewall: faqat 22/80/443 ochiq (`ufw status`)

## Kelajakda yangilash

Git orqali qilingan bo'lsa (2-bosqich A varianti), yangilanish shunchaki:

```bash
cd /opt/osonnavbat && git pull && docker compose -f docker-compose.prod.yml up -d --build
```

## Zaxira nusxa

```bash
docker compose -f docker-compose.prod.yml exec -T db pg_dump -U osonnavbat osonnavbat | gzip > backup-$(date +%F).sql.gz
```

Media fayllar `media` nomli Docker volume'da — uni ham nusxalang:

```bash
docker run --rm -v osonnavbat_media:/data -v "$PWD:/backup" alpine tar czf /backup/media-$(date +%F).tar.gz -C /data .
```
