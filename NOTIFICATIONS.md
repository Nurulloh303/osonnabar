# Xabarnomalar va Web Push — frontend uchun qo'llanma

Base URL: `https://api.qulaynavbat.uz/api/v1`

> **Eslatma:** TZ'da `web-push` (Node.js) kutubxonasi ko'rsatilgan edi. Backend
> Django/Python bo'lgani uchun uning Python ekvivalenti — `pywebpush` ishlatildi.
> Protokol bir xil (RFC 8291 + VAPID), shuning uchun **frontend tomonida hech qanday
> farq yo'q**: o'sha `applicationServerKey`, o'sha subscription obyekti.

---

## 1. API yo'nalishlari

| Metod | Manzil | Vazifasi |
|---|---|---|
| `GET` | `/notifications/vapid-key/` | Public VAPID kalit (auth talab qilinmaydi) |
| `POST` | `/notifications/subscribe/` | Brauzer obunasini saqlash |
| `POST` | `/notifications/unsubscribe/` | Obunani o'chirish |
| `GET` | `/notifications/subscriptions/` | Ulangan qurilmalarim |
| `GET` | `/notifications/` | Xabarlar tarixi (paginatsiya bilan) |
| `GET` | `/notifications/unread-count/` | O'qilmaganlar soni (qizil nuqtacha) |
| `PUT` | `/notifications/read/` | O'qilgan deb belgilash |
| `DELETE` | `/notifications/<id>/` | Bitta xabarni o'chirish |

Barchasi (`vapid-key` dan tashqari) autentifikatsiya talab qiladi va **faqat
joriy foydalanuvchining** ma'lumotlarini qaytaradi.

---

## 2. Obuna bo'lish (subscribe)

```js
const API = process.env.NEXT_PUBLIC_API_URL;

// base64url -> Uint8Array (brauzer shu formatni kutadi)
function urlBase64ToUint8Array(base64String) {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
  const raw = window.atob(base64);
  return Uint8Array.from([...raw].map((c) => c.charCodeAt(0)));
}

export async function enablePush() {
  if (!("serviceWorker" in navigator) || !("PushManager" in window)) return false;

  const permission = await Notification.requestPermission();
  if (permission !== "granted") return false;

  // 1. Public kalitni backenddan olamiz
  const { public_key, configured } = await fetch(`${API}/notifications/vapid-key/`)
    .then((r) => r.json());
  if (!configured) return false;

  // 2. Service worker'ni ro'yxatdan o'tkazamiz
  const registration = await navigator.serviceWorker.register("/sw.js");

  // 3. Obuna bo'lamiz
  const subscription = await registration.pushManager.subscribe({
    userVisibleOnly: true,
    applicationServerKey: urlBase64ToUint8Array(public_key),
  });

  // 4. Backendga saqlaymiz — subscription obyektini shundayligicha yuboramiz
  await fetch(`${API}/notifications/subscribe/`, {
    method: "POST",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": getCsrfToken(),
    },
    body: JSON.stringify(subscription),
  });

  return true;
}
```

`subscription.toJSON()` quyidagini beradi va backend aynan shuni kutadi:

```json
{
  "endpoint": "https://fcm.googleapis.com/fcm/send/...",
  "keys": { "p256dh": "...", "auth": "..." },
  "expirationTime": null
}
```

**Javob:** `201 Created`

Bir xil `endpoint` qayta yuborilsa yangi yozuv yaratilmaydi — mavjudi yangilanadi.
Bitta foydalanuvchi bir nechta qurilmadan obuna bo'lishi mumkin (telefon + noutbuk),
har biriga alohida xabar ketadi.

---

## 3. Service Worker (`public/sw.js`)

```js
self.addEventListener("push", (event) => {
  const data = event.data ? event.data.json() : {};
  event.waitUntil(
    self.registration.showNotification(data.title || "Qulay Navbat", {
      body: data.body || "",
      icon: "/icon-192.png",
      badge: "/badge-72.png",
      tag: data.id,
      data: { url: data.url },
    })
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = event.notification.data?.url || "/";
  event.waitUntil(clients.openWindow(url));
});
```

Push payload'i doim shu shaklda keladi:

```json
{
  "id": "uuid",
  "title": "Navbatingiz tasdiqlandi",
  "body": "Aziz Usta · 25.08.2026 11:00 · Soch olish",
  "kind": "booking_confirmed",
  "url": "/bookings/<uuid>"
}
```

---

## 4. Qo'ng'iroqcha (in-app)

```js
// Xabarlar ro'yxati
const data = await fetch(`${API}/notifications/`, { credentials: "include" })
  .then((r) => r.json());
// { count, page, pages, page_size, next, previous, results: [...] }

// Faqat o'qilmaganlar
fetch(`${API}/notifications/?is_read=false`, { credentials: "include" });

// Qizil nuqtacha uchun
const { unread } = await fetch(`${API}/notifications/unread-count/`, {
  credentials: "include",
}).then((r) => r.json());

// Hammasini o'qilgan deb belgilash (body bo'sh)
await fetch(`${API}/notifications/read/`, {
  method: "PUT",
  credentials: "include",
  headers: { "Content-Type": "application/json", "X-CSRFToken": getCsrfToken() },
  body: JSON.stringify({}),
});

// Faqat tanlanganlarni
body: JSON.stringify({ ids: ["uuid-1", "uuid-2"] })
```

`read/` javobi yangilangan sanoqni qaytaradi: `{ "unread": 0 }` — qo'shimcha
so'rov yubormasdan nuqtachani darhol o'chirish mumkin.

Bitta xabar obyekti:

```json
{
  "id": "uuid",
  "title": "Navbatingiz bekor qilindi",
  "body": "Aziz Usta · 25.08.2026 11:00. Sabab: Kasal bo'lib qoldim",
  "kind": "booking_cancelled",
  "kind_display": "Navbat bekor qilindi",
  "url": "/bookings/<uuid>",
  "booking_id": "uuid",
  "is_read": false,
  "created_at": "2026-08-23T14:05:00+0500"
}
```

---

## 5. Xabar turlari (`kind`)

| `kind` | Qachon | Kimga |
|---|---|---|
| `booking_created` | Mijoz navbatga yozildi | **Ustaga** |
| `booking_confirmed` | Usta tasdiqladi | Mijozga |
| `booking_cancelled` | **Usta** bekor qildi | Mijozga |
| `booking_completed` | Usta yakunladi | Mijozga |
| `booking_reminder` | Navbatga ~1 soat qoldi | Mijozga |
| `system` | Tizim xabari | — |

Mijoz **o'zi** bekor qilsa, unga xabar yuborilmaydi — u allaqachon biladi.

---

## 6. Muhim xatti-harakatlar

**Push ishlamasa ham xabar yo'qolmaydi.** Yozuv avval bazaga tushadi, keyin push
yuborilishga harakat qilinadi. Foydalanuvchi ruxsat bermagan bo'lsa ham,
qo'ng'iroqchada to'liq tarix ko'rinadi.

**O'lik obunalar avtomatik tozalanadi.** Push xizmati `404`/`410` qaytarsa
(foydalanuvchi brauzer ma'lumotlarini tozalagan), obuna bazadan o'chiriladi.

**VAPID sozlanmagan bo'lsa** `vapid-key` javobida `configured: false` keladi —
frontend push tugmasini ko'rsatmasligi kerak.

**Eslatmalar cron orqali.** Har 15 daqiqada ishlaydigan jarayon "45–75 daqiqa
qolgan" tasdiqlangan navbatlarni topadi. "Roppa-rosa 1 soat" deb qidirib
bo'lmaydi — cron uzluksiz ishlamaydi, shuning uchun oyna ishlatiladi. Bitta
navbatga ikkinchi marta eslatma ketmasligi `reminder_sent_at` bilan ta'minlangan.

---

## 7. Serverda sozlash

```bash
docker compose -f docker-compose.prod.yml exec api python manage.py generate_vapid_keys
```

Chiqqan ikkita qatorni `.env` ga qo'shing, so'ng:

```bash
docker compose -f docker-compose.prod.yml up -d
```

Eslatma cron'ini qo'lda sinash:

```bash
docker compose -f docker-compose.prod.yml exec api python manage.py send_booking_reminders --dry-run
```
