# API ma'lumotnomasi

Base URL: `https://api.qulaynavbat.uz/api/v1`

Mashina uchun to'liq spetsifikatsiya: [`schema.yml`](schema.yml) (OpenAPI 3).
Uni [editor.swagger.io](https://editor.swagger.io) ga tashlasangiz interaktiv
hujjat chiqadi, yoki `openapi-typescript` bilan TS tiplarini generatsiya qilasiz:

```bash
npx openapi-typescript schema.yml -o src/types/api.d.ts
```

---

## ⚠️ Manzillarda tez-tez adashilyapti

| Noto'g'ri | To'g'ri | Izoh |
|---|---|---|
| `/barbers/me/` | **`/barber/me/`** | Birlikda — usta o'z profili |
| `POST /barbers/` | **`POST /super-admin/barbers/`** | `/barbers/` — ochiq katalog, faqat `GET` |
| `POST /salons/` | **`POST /super-admin/salons/`** | `/salons/` — ochiq katalog, faqat `GET` |
| `/auth/users/` | **`/super-admin/users/`** | |

`405` = manzil bor, lekin bu metodni qabul qilmaydi.
`404` = manzil umuman yo'q.

---

## 1. Usta o'z profilini boshqarish

### `GET /barber/me/`

```json
{
  "id": "3d96ea61-6cfb-40f4-9175-bdf125fb2d98",
  "profile": {
    "id": "90d20069-0f1a-4c02-95eb-dab82cce263d",
    "phone": null,
    "email": "aziz@gmail.com",
    "full_name": "Aziz Karimov",
    "role": "barber",
    "avatar": null,
    "is_phone_verified": false,
    "is_active": true,
    "barber_id": "3d96ea61-6cfb-40f4-9175-bdf125fb2d98",
    "is_profile_complete": true,
    "created_at": "2026-09-05T11:31:25+0500"
  },
  "salon": "0d25a3c6-9327-4571-a289-6846a66af1ed",
  "specialty": "men",
  "status": "active",
  "bio": "10 yillik tajriba",
  "experience_years": 10,
  "avatar": null,
  "location_lat": null,
  "location_lng": null,
  "services": [
    { "name": "Soch olish", "price": 50000, "duration_minutes": 30 },
    { "name": "Soqol olish", "price": 30000, "duration_minutes": 20 }
  ],
  "default_slot_minutes": 30,
  "rating_avg": 5.0,
  "reviews_count": 1,
  "completed_bookings": 0
}
```

### `PATCH /barber/me/` — tahrirlash

O'zgartirsa bo'ladigan maydonlar: `bio`, `experience_years`, `specialty`,
`salon`, `avatar`, `location_lat`, `location_lng`, `services`, `default_slot_minutes`.

**Faqat o'qish uchun:** `status`, `rating_avg`, `reviews_count`,
`completed_bookings`, `profile` (ism/email `PATCH /auth/me/` orqali).

**Xizmatlar ro'yxati — to'liq almashtiriladi** (qo'shish/o'chirish/tahrirlash
alohida endpoint emas). Yangi ro'yxatni butunligicha yuboring:

```json
PATCH /barber/me/
{
  "bio": "Yangilangan tavsif",
  "services": [
    { "name": "Soch olish", "price": 60000, "duration_minutes": 30 },
    { "name": "Bolalar sochi", "price": 35000, "duration_minutes": 20 }
  ]
}
```

`duration_minutes` ixtiyoriy (default 30), `10`–`240` oralig'ida.
Xizmat nomlari **takrorlanmasligi** kerak (registr hisobga olinmaydi) — aks holda 400.

⚠️ Bron yaratishda narx va davomiylik **shu ro'yxatdan** olinadi, mijoz o'zi
yubora olmaydi. Xizmat nomini o'zgartirsangiz, eski bronlar tegilmaydi.

### Usta jadvali

| Metod | Manzil |
|---|---|
| `GET` `POST` | `/barber/me/schedule/` |
| `PUT` | `/barber/me/schedule/bulk/` — 7 kunni bir zarbda |
| `GET` `PATCH` `DELETE` | `/barber/me/schedule/<id>/` |
| `GET` | `/barber/me/schedule/weekdays/` — kunlar lug'ati |
| `GET` `POST` `DELETE` | `/barber/me/days-off/` |
| `GET` | `/barber/me/stats/?period=day\|week\|month\|year\|all` |

`bulk` namunasi:

```json
PUT /barber/me/schedule/bulk/
[
  { "weekday": 0, "is_working": true, "start_time": "10:00", "end_time": "19:00",
    "break_start": "13:00", "break_end": "14:00", "slot_minutes": 30 },
  { "weekday": 6, "is_working": false, "start_time": "10:00", "end_time": "19:00" }
]
```

`weekday`: `0`=Dushanba … `6`=Yakshanba. Tanaffus ikkalasi birga bo'lishi kerak.

---

## 2. Rasm (photo)

Rasm maydoni **bor** va `multipart/form-data` bilan yuboriladi (base64 emas, URL emas).

```js
const form = new FormData();
form.append("avatar", file);           // <input type="file">

await fetch(`${API}/barber/me/`, {
  method: "PATCH",
  credentials: "include",
  headers: { "X-CSRFToken": getCookie("csrftoken") },  // Content-Type QO'YMANG
  body: form,
});
```

> `Content-Type` ni o'zingiz qo'ymang — brauzer `boundary` bilan birga o'zi qo'yadi.

**Qayerda:**

| Manzil | Kim |
|---|---|
| `PATCH /barber/me/` | Usta o'z rasmini |
| `PATCH /super-admin/barbers/<id>/` | Admin istalgan ustaning rasmini |
| `POST` `DELETE` `/auth/me/avatar/` | Har kim o'z profil rasmini |
| `PATCH /super-admin/salons/<id>/` | Salon muqovasi (`cover_image`) |

**Cheklovlar:** maksimal **5 MB**, faqat `jpg` / `png` / `webp` / `gif`.
Fayl nomi hisobga olinmaydi — format Pillow bilan tekshiriladi, shuning uchun
`rasm.html` deb nomlangan fayl qabul qilinmaydi (400).

**Javobda** to'liq URL keladi:
```json
"avatar": "https://api.qulaynavbat.uz/media/barbers/<uuid>.png"
```

`/barbers/` javobidagi `avatar` — ustaning o'z rasmi, u bo'lmasa profil rasmi
(`profile.avatar`). Ikkalasi ham bo'lmasa `null`.

⚠️ **Usta yaratishda rasm yuborib bo'lmaydi** (`POST /super-admin/barbers/`).
Avval yarating, keyin `PATCH /super-admin/barbers/<id>/` bilan rasm yuklang.

---

## 3. Bronlar

### Bron yaratish

```json
POST /bookings/
{
  "barber": "d4b94aca-6466-4b81-aa74-74ab5eba3c02",
  "booking_date": "2026-09-06",
  "booking_time": "11:00",
  "service_name": "Soch olish",
  "client_note": "Iltimos, qisqaroq oling"
}
```

⚠️ **`price` va `duration_minutes` yubormang** — ular ustaning xizmatlar
ro'yxatidan server tomonda olinadi. Yuborsangiz e'tiborsiz qoldiriladi.
`service_name` ustaning ro'yxatidagi nom bilan mos kelishi kerak (registr muhim emas).

Faqat **mijoz** (`role: client`) yozila oladi.

### Javob (`201`)

```json
{
  "id": "bf6ee2b4-6d46-465b-b081-eca61c0b99dd",
  "client": { "id": "...", "full_name": "Bobur Aliyev", "phone": null, "avatar": null },
  "barber": { "id": "...", "full_name": "Aziz Karimov", "avatar": null,
              "specialty": "men", "rating_avg": 5.0, "reviews_count": 1, "status": "active" },
  "salon":  { "id": "...", "name": "Zamon Barbershop", "address": "...", "district": "Yunusobod",
              "city": "Toshkent", "location_lat": 41.311081, "location_lng": 69.240562 },
  "booking_date": "2026-09-06",
  "booking_time": "11:00",
  "duration_minutes": 30,
  "starts_at": "2026-09-06T11:00:00+0500",
  "ends_at": "2026-09-06T11:30:00+0500",
  "service_name": "Soch olish",
  "price": 50000,
  "status": "pending",
  "status_display": "Kutilmoqda",
  "client_note": "",
  "cancel_reason": "",
  "confirmed_at": null,
  "completed_at": null,
  "cancelled_at": null,
  "can_cancel": true,
  "can_review": false,
  "created_at": "2026-09-05T11:31:25+0500"
}
```

`can_cancel` / `can_review` — server hisoblab beradi, tugmalarni shularga qarab
ko'rsating (o'zingiz qoida yozmang).

### Xatolar

| Kod | Status | Sabab |
|---|---|---|
| `slot_taken` | 409 | Bu vaqt band |
| `business_rule` | 400 | Biznes qoidasi buzilgan |
| `invalid` | 400 | Validatsiya (xizmat yo'q, ish vaqtidan tashqari, o'tgan sana…) |

Har doim shu shaklda: `{ "detail": "...", "code": "...", "errors": {...} }`

### Ro'yxat

`GET /bookings/` — **rolga qarab avtomatik filtrlanadi**: mijoz o'zinikini,
usta o'ziga tushganini, super admin hammasini ko'radi. Alohida `?barber=`
yuborish shart emas.

| Parametr | Misol |
|---|---|
| `scope` | `?scope=upcoming` / `past` / `today` |
| `status` | `?status=pending&status=confirmed` |
| sana | `?date_from=2026-09-01&date_to=2026-09-30` |
| tartib | `?ordering=booking_date` / `-booking_date` |
| qidiruv | `?search=Aziz` |

**Ustaning bugungi jadvali:** `GET /bookings/?scope=today`

`GET /bookings/counts/` → `{"pending":0,"confirmed":0,"completed":1,"cancelled":0}`
(filtrlar bilan birga ishlaydi)

### Holatni o'zgartirish

| Manzil | Kim | Shart |
|---|---|---|
| `POST /bookings/<id>/confirm/` | usta | faqat `pending` dan |
| `POST /bookings/<id>/complete/` | usta | `pending` yoki `confirmed` dan |
| `POST /bookings/<id>/cancel/` | mijoz, usta, admin | body: `{"reason":"..."}` (ixtiyoriy) |

Body kerak emas (`cancel` dan tashqari). Javob — yangilangan bron obyekti.

**Holatlar:** `pending` → `confirmed` → `completed`, istalgan paytda `cancelled`.

Mijoz boshlanishiga **60 daqiqadan kam** qolganda bekor qila olmaydi
(`can_cancel: false` bo'ladi). Usta va admin uchun bu cheklov yo'q.

### Bo'sh vaqtlar

```
GET /barbers/<id>/available-slots/?date=2026-09-06&service=Soch%20olish
```

```json
{
  "barber_id": "...",
  "date": "2026-09-06",
  "weekday": 6,
  "is_working_day": true,
  "slot_minutes": 30,
  "slots": [
    { "time": "09:00", "is_available": false, "reason": "past" },
    { "time": "11:00", "is_available": false, "reason": "booked" },
    { "time": "13:00", "is_available": false, "reason": "break" },
    { "time": "14:00", "is_available": true,  "reason": null }
  ]
}
```

Band vaqtlar ham qaytadi — kulrang qilib ko'rsatish uchun.
`reason`: `past` | `booked` | `break`.
`service` bersangiz, o'sha xizmat davomiyligi hisobga olinadi.

`GET /barbers/<id>/next-slot/` → `{"next_slot": {"date":"2026-09-06","time":"14:00"}}`

### Boshqa qoidalar

- Bir mijozda bir vaqtda **5 tadan ko'p** faol bron bo'lmaydi
- Bitta ustaga bitta kunga **bitta** bron
- Faqat **30 kun** oldinga

---

## 4. Aniqlik kiritilgan savollar

### `specialty` kodlari

`men` · `women` · `kids` · `unisex` — **ham salon, ham usta uchun bir xil**.
Sizdagi mapping to'g'ri.

### `/barbers/` javobi

`salon` **ichma-ich** keladi (`id`, `name`, `address`, `district`, `city`,
`location_lat`, `location_lng`). `services`, `rating_avg`, `reviews_count`,
`price_from` (eng arzon xizmat narxi) ham bor.

**Xaritadagi nuqta:** yuqori darajadagi `location_lat` / `location_lng` ni
ishlating — server ustaning o'z koordinatasini, u bo'lmasa salonnikini
qo'yib beradi. `salon.location_*` ni o'zingiz olishingiz shart emas.

Geo qidiruv: `?lat=41.31&lng=69.24&radius=5` → javobga `distance_km` qo'shiladi
va natija masofa bo'yicha saralanadi. `radius` — km, ixtiyoriy.

`GET /barbers/<id>/` qo'shimcha `schedules` (7 kunlik jadval) va `days_off`
(kelgusi 60 kun, `["2026-09-10", ...]`) qaytaradi.

### `/super-admin/stats/`

```json
{
  "period": "month",
  "period_from": "2026-09-01",
  "users":    { "clients": 1, "barbers": 1, "blocked": 0, "new_this_month": 3 },
  "barbers":  { "total": 1, "active": 1, "blocked": 0 },
  "salons":   { "total": 1, "active": 1 },
  "bookings": { "total": 1, "pending": 0, "confirmed": 0, "completed": 1, "cancelled": 0,
                "today_total": 0, "revenue_total": 50000, "revenue_today": 0,
                "revenue_month": 50000, "avg_check": 50000.0 },
  "period_totals": { "bookings": 1, "revenue": 50000 },
  "chart": [ { "date": "2026-08-07", "revenue": 0, "bookings": 0 } ],
  "top_barbers": [ { "id": "...", "profile__full_name": "Aziz Karimov",
                     "salon__name": "Zamon Barbershop", "revenue": 50000,
                     "orders": 1, "rating_avg": 5.0 } ]
}
```

`chart` — doim **30 kun**, bo'sh kunlar `0` bilan to'ldirilgan (grafikda uzilish
bo'lmaydi). `avg_check` — `null` bo'lishi mumkin. Daromad faqat `completed`
bronlardan hisoblanadi. `?period=` faqat `period_totals` ga ta'sir qiladi.

`GET /barber/me/stats/` shakli o'xshash: `totals`, `period_totals`,
`rating: {average, reviews}`, `chart`, `top_services`.

### `/super-admin/users/` maydonlari

Taxminingizda uchta nom noto'g'ri:

| Siz o'ylagan | Haqiqiy |
|---|---|
| `is_blocked` | **`is_active`** (teskari ma'no! `false` = bloklangan) |
| `date_joined` | **`created_at`** |
| `avatar` | `avatar` ✅ bor |

To'liq: `id`, `phone`, `email`, `full_name`, `role`, `avatar`, `is_active`,
`is_phone_verified`, `bookings_count`, `total_spent`, `barber_id`,
`created_at`, `last_login`.

`role`: `client` | `barber` | `superadmin` ✅ to'g'ri.

⚠️ `phone` **`null` bo'lishi mumkin** (Google orqali kirganlar).

Filtrlar: `?role=barber`, `?is_active=false`, `?search=`,
`?ordering=created_at|full_name|last_login`.

Amallar: `POST .../block/`, `.../unblock/`, `.../set-role/` (`{"role":"barber"}`).
Ro'yxat **faqat o'qish** — foydalanuvchi yaratish endpointi yo'q, akkaunt
Google orqali kirganda avtomatik ochiladi.

### `POST /super-admin/salons/` javobi

Ha, `id` qaytadi — **UUID** (`"0d25a3c6-9327-4571-a289-6846a66af1ed"`).
Loyihadagi barcha `id` lar UUID. Uni to'g'ridan-to'g'ri usta yaratishda
`salon` maydoniga bering.

### `page_size`

Maksimum **100**. `?page_size=100` to'g'ri ishlaydi, undan kattasi 100 ga
tushiriladi (xato bermaydi). Default 20.

Paginatsiya: `{ count, page, pages, page_size, next, previous, results }`.

---

## 5. Qolgan ikkitasi

### Ustalik arizalari

Bunday endpoint **yo'q**. Sizdagi yechim (frontendda navbat → admin tasdiqlaganda
`POST /super-admin/salons/` + `POST /super-admin/barbers/`) hozircha to'g'ri.

Serverda tursin desangiz ayting — jadval + `GET/POST /barber-applications/` +
`POST .../approve/` (tasdiqlanganda usta avtomatik yaratiladi) qo'shib beraman.
Foydasi: arizalar brauzer xotirasida yo'qolmaydi va bir nechta admin ko'ra oladi.

### Reyting

**To'liq avtomatik.** Sharh qo'shilganda/o'chirilganda signal ishga tushib,
`Barber.rating_avg` va `reviews_count` qayta hisoblanadi, keyin salonniki ham.
Siz hech narsa qilmaysiz — `/barbers/` javobidagi `rating_avg` doim to'g'ri.

```json
POST /reviews/
{ "booking": "<booking-uuid>", "rating": 5, "comment": "Zo'r ish!" }
```

Sharh **faqat yakunlangan bron uchun** va **faqat bron egasi** tomonidan.
Bitta bronga bitta sharh (`can_review` shuni tekshiradi).
`barber`, `salon`, `client` — bronidan avtomatik olinadi, yubormang.

Javob:

```json
{
  "id": "...",
  "booking": "<booking-uuid>",
  "barber": "<barber-uuid>",
  "salon": "<salon-uuid>",
  "client": { "id": "...", "full_name": "Bobur A.", "avatar": null },
  "service_name": "Soch olish",
  "rating": 5,
  "comment": "Zo'r ish!",
  "barber_reply": "",
  "created_at": "2026-09-05T11:31:25+0500"
}
```

⚠️ `client.full_name` — **qisqartirilgan** (`"Bobur Aliyev"` → `"Bobur A."`).
Maxfiylik uchun ataylab: sharhlar hammaga ochiq. To'liq ismni ko'rsatmang.

- `GET /reviews/?barber=<id>` — ustaning sharhlari
- `GET /reviews/summary/?barber=<id>` → `{ "total": 1, "average": 5.0, "distribution": {"1":0,...,"5":1} }`
- `POST /reviews/<id>/reply/` — usta javob yozadi (`{"barber_reply":"Rahmat!"}`)
- `DELETE /reviews/<id>/` — muallif yoki admin

---

## Eslatma

Barcha so'rovlarda `credentials: "include"`, o'zgartiruvchi so'rovlarda
`X-CSRFToken`. Kirish — [AUTH.md](AUTH.md), xabarnomalar — [NOTIFICATIONS.md](NOTIFICATIONS.md).
