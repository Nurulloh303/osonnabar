"""Demo ma'lumotlar: `python manage.py seed_demo`

Frontend'ni real ma'lumotsiz ham to'liq sinab ko'rish uchun Toshkent
koordinatalari bilan salonlar, ustalar, jadvallar, bronlar va sharhlar yaratadi.
Qayta ishga tushirsa dublikat yaratmaydi (get_or_create).
"""

import random
from datetime import date, time, timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.bookings.models import Booking, BookingStatus
from apps.reviews.models import Review
from apps.salons.models import Barber, BarberSchedule, Salon, Specialty

User = get_user_model()

SALONS = [
    ("Barber King", Specialty.MEN, "Amir Temur ko'chasi, 42", "Yunusobod", 41.3311, 69.2797),
    ("Glamour Beauty", Specialty.WOMEN, "Bunyodkor shoh ko'chasi, 12", "Chilonzor", 41.2856, 69.2034),
    ("Style Studio", Specialty.UNISEX, "Shota Rustaveli, 7", "Yakkasaroy", 41.2857, 69.2413),
    ("Kids Cut", Specialty.KIDS, "Mustaqillik shoh ko'chasi, 90", "Mirzo Ulug'bek", 41.3255, 69.3384),
    ("Elite Barbershop", Specialty.MEN, "Navoiy ko'chasi, 30", "Shayxontohur", 41.3193, 69.2401),
    ("Aurora Salon", Specialty.WOMEN, "Buyuk Ipak Yo'li, 158", "Mirzo Ulug'bek", 41.3283, 69.3120),
]

BARBERS = [
    ("+998901000001", "Jasur Rahimov", Specialty.MEN, 0, 8),
    ("+998901000002", "Aziz Karimov", Specialty.MEN, 0, 5),
    ("+998901000003", "Malika Yusupova", Specialty.WOMEN, 1, 10),
    ("+998901000004", "Nigora Tosheva", Specialty.WOMEN, 1, 6),
    ("+998901000005", "Sardor Aliyev", Specialty.UNISEX, 2, 4),
    ("+998901000006", "Dilnoza Sobirova", Specialty.UNISEX, 2, 7),
    ("+998901000007", "Bekzod Umarov", Specialty.KIDS, 3, 3),
    ("+998901000008", "Otabek Nazarov", Specialty.MEN, 4, 12),
    ("+998901000009", "Kamola Yo'ldosheva", Specialty.WOMEN, 5, 9),
]

CLIENTS = [
    ("+998907000001", "Nurulloh Abdullayev"),
    ("+998907000002", "Shahzod Tursunov"),
    ("+998907000003", "Zilola Ergasheva"),
    ("+998907000004", "Javohir Qodirov"),
    ("+998907000005", "Madina Sultonova"),
    ("+998907000006", "Ulug'bek Sattorov"),
]

SERVICES_BY_SPECIALTY = {
    Specialty.MEN: [
        {"name": "Soch olish", "price": 50000, "duration_minutes": 30},
        {"name": "Soqol olish", "price": 30000, "duration_minutes": 20},
        {"name": "Soch + soqol", "price": 70000, "duration_minutes": 50},
        {"name": "Bolalar soch olish", "price": 40000, "duration_minutes": 30},
    ],
    Specialty.WOMEN: [
        {"name": "Soch turmagi", "price": 120000, "duration_minutes": 60},
        {"name": "Bo'yash", "price": 250000, "duration_minutes": 120},
        {"name": "Manikyur", "price": 80000, "duration_minutes": 60},
        {"name": "Makiyaj", "price": 150000, "duration_minutes": 60},
    ],
    Specialty.KIDS: [
        {"name": "Bolalar soch olish", "price": 40000, "duration_minutes": 30},
        {"name": "Bolalar dizayn", "price": 60000, "duration_minutes": 40},
    ],
    Specialty.UNISEX: [
        {"name": "Soch olish", "price": 60000, "duration_minutes": 30},
        {"name": "Soch turmagi", "price": 110000, "duration_minutes": 60},
        {"name": "Qosh dizayni", "price": 45000, "duration_minutes": 30},
    ],
}

COMMENTS = [
    "Juda mamnunman, rahmat!",
    "Tez va sifatli xizmat.",
    "Usta ishini yaxshi biladi, albatta yana boraman.",
    "Yaxshi, lekin biroz kutishga to'g'ri keldi.",
    "Salon toza, muhit yoqimli.",
    "Narxi ham arzon, natija ham zo'r.",
]


class Command(BaseCommand):
    help = "Demo ma'lumotlarni yaratadi (salonlar, ustalar, mijozlar, bronlar, sharhlar)."

    def add_arguments(self, parser):
        parser.add_argument("--bookings", type=int, default=120, help="Yaratiladigan bronlar soni")
        parser.add_argument("--flush", action="store_true", help="Avval demo bronlar/sharhlarni o'chirish")

    @transaction.atomic
    def handle(self, *args, **options):
        random.seed(2026)

        if options["flush"]:
            Review.objects.all().delete()
            Booking.objects.all().delete()
            self.stdout.write(self.style.WARNING("Eski bronlar va sharhlar o'chirildi."))

        admin = self._create_superadmin()
        salons = self._create_salons()
        barbers = self._create_barbers(salons)
        clients = self._create_clients()
        created = self._create_bookings(barbers, clients, options["bookings"])
        reviews = self._create_reviews()

        self.stdout.write(self.style.SUCCESS("\n✓ Demo ma'lumotlar tayyor"))
        self.stdout.write(f"  Salonlar : {len(salons)}")
        self.stdout.write(f"  Ustalar  : {len(barbers)}")
        self.stdout.write(f"  Mijozlar : {len(clients)}")
        self.stdout.write(f"  Bronlar  : {created}")
        self.stdout.write(f"  Sharhlar : {reviews}")
        self.stdout.write(
            self.style.HTTP_INFO(
                f"\n  Super admin : {admin.phone} (parol: admin12345 — /admin/ uchun)\n"
                f"  Usta        : {BARBERS[0][0]}\n"
                f"  Mijoz       : {CLIENTS[0][0]}\n"
                "  OTP kodi konsolga chiqadi (SMS_BACKEND=console)."
            )
        )

    # ── bosqichlar ────────────────────────────────────────────────────
    def _create_superadmin(self):
        admin, created = User.objects.get_or_create(
            phone="+998901111111",
            defaults={
                "full_name": "Super Admin",
                "role": User.Role.SUPERADMIN,
                "is_staff": True,
                "is_superuser": True,
                "is_phone_verified": True,
            },
        )
        if created:
            admin.set_password("admin12345")
            admin.save(update_fields=["password"])
        return admin

    def _create_salons(self):
        salons = []
        for name, specialty, address, district, lat, lng in SALONS:
            salon, _ = Salon.objects.get_or_create(
                name=name,
                defaults={
                    "specialty": specialty,
                    "address": address,
                    "district": district,
                    "location_lat": lat,
                    "location_lng": lng,
                    "phone": "+998712000000",
                    "description": f"{name} — {district} tumanidagi zamonaviy salon.",
                },
            )
            salons.append(salon)
        return salons

    def _create_barbers(self, salons):
        barbers = []
        for phone, full_name, specialty, salon_idx, experience in BARBERS:
            user, _ = User.objects.get_or_create(
                phone=phone,
                defaults={"full_name": full_name, "role": User.Role.BARBER, "is_phone_verified": True},
            )
            salon = salons[salon_idx]
            barber, created = Barber.objects.get_or_create(
                profile=user,
                defaults={
                    "salon": salon,
                    "specialty": specialty,
                    "experience_years": experience,
                    "bio": f"{experience} yillik tajribaga ega usta.",
                    "services": SERVICES_BY_SPECIALTY[specialty],
                    "location_lat": salon.location_lat + random.uniform(-0.004, 0.004),
                    "location_lng": salon.location_lng + random.uniform(-0.004, 0.004),
                },
            )
            if created:
                self._create_schedule(barber)
            barbers.append(barber)
        return barbers

    def _create_schedule(self, barber: Barber):
        for weekday in range(7):
            BarberSchedule.objects.get_or_create(
                barber=barber,
                weekday=weekday,
                defaults={
                    "is_working": weekday != 6,  # yakshanba dam
                    "start_time": time(9, 0),
                    "end_time": time(20, 0) if weekday < 5 else time(18, 0),
                    "break_start": time(13, 0),
                    "break_end": time(14, 0),
                    "slot_minutes": 30,
                },
            )

    def _create_clients(self):
        clients = []
        for phone, full_name in CLIENTS:
            user, _ = User.objects.get_or_create(
                phone=phone,
                defaults={"full_name": full_name, "role": User.Role.CLIENT, "is_phone_verified": True},
            )
            clients.append(user)
        return clients

    def _create_bookings(self, barbers, clients, count: int) -> int:
        today = timezone.localdate()
        created = 0
        attempts = 0

        while created < count and attempts < count * 6:
            attempts += 1
            barber = random.choice(barbers)
            client = random.choice(clients)
            service = random.choice(barber.services)

            offset = random.randint(-30, 10)
            day: date = today + timedelta(days=offset)
            if day.weekday() == 6:
                continue

            hour = random.randint(9, 18)
            minute = random.choice([0, 30])
            if hour == 13:
                continue

            if offset < 0:
                status = random.choices(
                    [BookingStatus.COMPLETED, BookingStatus.CANCELLED], weights=[85, 15]
                )[0]
            elif offset == 0:
                status = random.choice([BookingStatus.CONFIRMED, BookingStatus.COMPLETED])
            else:
                status = random.choices(
                    [BookingStatus.PENDING, BookingStatus.CONFIRMED], weights=[40, 60]
                )[0]

            _, was_created = Booking.objects.get_or_create(
                barber=barber,
                booking_date=day,
                booking_time=time(hour, minute),
                defaults={
                    "client": client,
                    "salon": barber.salon,
                    "service_name": service["name"],
                    "price": service["price"],
                    "duration_minutes": service.get("duration_minutes", 30),
                    "status": status,
                    "confirmed_at": timezone.now() if status != BookingStatus.PENDING else None,
                    "completed_at": timezone.now() if status == BookingStatus.COMPLETED else None,
                },
            )
            if was_created:
                created += 1

        for barber in barbers:
            barber.completed_bookings = barber.bookings.filter(status=BookingStatus.COMPLETED).count()
            barber.save(update_fields=["completed_bookings"])

        return created

    def _create_reviews(self) -> int:
        completed = Booking.objects.filter(status=BookingStatus.COMPLETED, review__isnull=True)
        created = 0
        for booking in completed:
            if random.random() > 0.6:
                continue
            Review.objects.create(
                booking=booking,
                client=booking.client,
                barber=booking.barber,
                salon=booking.salon,
                rating=random.choices([5, 4, 3], weights=[70, 25, 5])[0],
                comment=random.choice(COMMENTS),
            )
            created += 1
        return created
