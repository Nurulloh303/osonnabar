# Ro'yxatdan o'tish va kirish — Google Sign-In

Base URL: `https://api.qulaynavbat.uz/api/v1`

**Telefon + SMS kod o'chirilgan.** Yagona kirish yo'li — Google akkaunt.
`/auth/otp/request/` va `/auth/otp/verify/` manzillari endi **404** qaytaradi.

---

## 1. Google Cloud Console sozlamasi (bir marta)

[console.cloud.google.com](https://console.cloud.google.com) da:

1. Loyiha yarating yoki mavjudini tanlang
2. **APIs & Services → OAuth consent screen** → `External` → nomi, logotipi,
   yordam emailini to'ldiring
3. **APIs & Services → Credentials → Create Credentials → OAuth client ID**
   - Application type: **Web application**
   - **Authorized JavaScript origins:**
     ```
     https://qulaynavbat.uz
     https://www.qulaynavbat.uz
     http://localhost:3000
     ```
4. Chiqqan **Client ID** (`...apps.googleusercontent.com`) — backendga ham,
   frontendga ham shu kerak. **Client secret** kerak emas.

> Backend faqat Google bergan `id_token` ni tekshiradi (imzo + `aud` + `iss` +
> `email_verified`), shuning uchun secret saqlanmaydi.

---

## 2. Qaysi usullar yoqilganini bilish

```js
const { google, google_client_id, sms } =
  await fetch(`${API}/auth/methods/`).then(r => r.json());
```

```json
{ "google": true, "google_client_id": "123-abc.apps.googleusercontent.com", "sms": false }
```

Auth talab qilinmaydi. Client ID'ni shu yerdan olsangiz, frontend `.env` ga
qo'shish shart emas va u backend bilan doim mos bo'ladi.

---

## 3. Kirish oqimi

### Next.js + `@react-oauth/google`

```bash
npm install @react-oauth/google
```

```jsx
import { GoogleOAuthProvider, GoogleLogin } from "@react-oauth/google";

function LoginButton({ clientId }) {
  const handleSuccess = async (credentialResponse) => {
    // 1. CSRF token olamiz (cookie o'rnatiladi)
    await fetch(`${API}/auth/csrf/`, { credentials: "include" });

    // 2. Google bergan credential (id_token) ni backendga yuboramiz
    const res = await fetch(`${API}/auth/google/`, {
      method: "POST",
      credentials: "include",           // ⚠️ majburiy
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": getCookie("csrftoken"),
      },
      body: JSON.stringify({ id_token: credentialResponse.credential }),
    });

    const data = await res.json();
    // data.user       -> profil
    // data.is_new_user -> true bo'lsa "xush kelibsiz" ekranini ko'rsatish mumkin
  };

  return (
    <GoogleOAuthProvider clientId={clientId}>
      <GoogleLogin onSuccess={handleSuccess} onError={() => alert("Kirish bekor qilindi")} />
    </GoogleOAuthProvider>
  );
}
```

`clientId` ni `/auth/methods/` dan oling.

### Javob

```json
{
  "user": {
    "id": "uuid",
    "phone": null,
    "email": "mijoz@gmail.com",
    "full_name": "Ism Familiya",
    "role": "client",
    "avatar": null,
    "is_phone_verified": false,
    "is_active": true,
    "barber_id": null,
    "is_profile_complete": true,
    "created_at": "2026-09-01T20:00:00+0500"
  },
  "is_new_user": true
}
```

Tokenlar javobda **yo'q** — ular `httpOnly` cookie'ga yoziladi
(`on_access`, `on_refresh`). JS ularni o'qiy olmaydi, bu ataylab shunday.

---

## 4. Muhim jihatlar

**`phone` endi `null` bo'lishi mumkin.** Google akkauntda telefon yo'q.
Profil sahifasida telefon ko'rsatayotgan joylar buni hisobga olsin.
Kerak bo'lsa keyinroq telefon so'rash alohida qo'shiladi.

**Roli saqlanadi.** Admin ustani **email bilan** yaratadi. Usta o'sha email
bilan Google'da kirganda backend mavjud akkauntni topib bog'laydi va
`role: "barber"` saqlanib qoladi — yangi mijoz akkaunti ochilmaydi.

**Xatolar:**

| Kod | Holat | Nima qilish |
|---|---|---|
| `google_no_email` | 400 | Google akkauntda email ko'rinmadi — email ruxsatini so'rang |
| `account_blocked` | 403 | Akkaunt bloklangan — administratorga murojaat |
| — | 401/403 | `GOOGLE_CLIENT_ID` backendda sozlanmagan |
| — | 429 | Limitga urildi (soatiga 30 ta urinish) |

**Keyingi so'rovlar.** Kirgandan keyin hamma narsa avvalgidek:
`credentials: "include"` + o'zgartiruvchi so'rovlarda `X-CSRFToken`.

**Sessiya muddati.** Access token 30 daqiqa. 401 kelsa
`POST /auth/refresh/` chaqiring (u ham cookie bilan ishlaydi), keyin so'rovni
takrorlang. Refresh ham 401 bersa — qaytadan Google orqali kirish kerak.

---

## 5. Ustalarni qo'shish (super admin)

`POST /api/v1/super-admin/barbers/`

```json
{
  "email": "usta@gmail.com",
  "full_name": "Aziz Karimov",
  "phone": "901234567",
  "specialty": "men",
  "services": [{ "name": "Soch olish", "price": 50000, "duration_minutes": 30 }]
}
```

- `email` — **majburiy**, ustaning Google akkaunti. Noto'g'ri bo'lsa usta
  kirganda o'ziga alohida "mijoz" akkaunti ochilib ketadi va paneliga kira olmaydi.
- `phone` — ixtiyoriy, faqat bog'lanish uchun.
