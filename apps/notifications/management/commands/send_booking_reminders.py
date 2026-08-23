"""Navbat boshlanishidan oldin eslatma yuboradi (cron).

Har 15 daqiqada ishlaydi va "1 soat qolgan" navbatlarni topadi.

⚠️ "Roppa-rosa 1 soat" deb qidirib bo'lmaydi: cron 15 daqiqada bir ishlaydi,
demak 10:00 dagi navbat uchun aynan 09:00 da tekshiruvga tushish kafolati yo'q.
Shuning uchun **oyna** (window) ishlatiladi — masalan 45–75 daqiqa oralig'i.
Oynalar bir-birining ustiga tushishi mumkin, shuning uchun `Booking.reminder_sent_at`
belgisi qo'yiladi va bitta navbatga ikkinchi marta eslatma ketmaydi.
"""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.bookings.models import Booking, BookingStatus
from apps.notifications import services


class Command(BaseCommand):
    help = "Yaqinlashayotgan navbatlar uchun eslatma yuboradi (cron uchun)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--lead-minutes",
            type=int,
            default=60,
            help="Navbatgacha qancha vaqt qolganda eslatilsin (default: 60).",
        )
        parser.add_argument(
            "--window-minutes",
            type=int,
            default=15,
            help="Oynaning yarim kengligi — cron oralig'iga teng bo'lsin (default: 15).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Hech narsa yubormaydi, faqat kimga ketishini ko'rsatadi.",
        )

    def handle(self, *args, **options):
        lead = options["lead_minutes"]
        window = options["window_minutes"]
        dry_run = options["dry_run"]

        now = timezone.now()
        earliest = now + timedelta(minutes=lead - window)
        latest = now + timedelta(minutes=lead + window)

        # `starts_at` — Python xossasi (sana + vaqt), SQL'da yo'q. Shuning uchun
        # avval sana bo'yicha toraytiramiz (indeksdan foydalanadi), keyin aniq
        # vaqtni Python'da tekshiramiz. Oyna 2 soatdan kichik bo'lgani uchun
        # bu ko'pi bilan ikkita kunni qamrab oladi.
        candidate_dates = {
            timezone.localtime(earliest).date(),
            timezone.localtime(latest).date(),
        }

        candidates = (
            Booking.objects.filter(
                status=BookingStatus.CONFIRMED,
                reminder_sent_at__isnull=True,
                booking_date__in=candidate_dates,
            )
            .select_related("client", "barber__profile", "salon")
            .order_by("booking_date", "booking_time")
        )

        sent = 0
        for booking in candidates:
            starts_at = booking.starts_at
            if not (earliest <= starts_at <= latest):
                continue

            minutes_left = int((starts_at - now).total_seconds() // 60)

            if dry_run:
                self.stdout.write(
                    f"  [dry-run] {booking.client.display_name} <- {booking.id} "
                    f"({minutes_left} daqiqa qoldi)"
                )
                sent += 1
                continue

            services.booking_reminder(booking, minutes_left)
            Booking.objects.filter(pk=booking.pk).update(reminder_sent_at=now)
            sent += 1

        if sent:
            self.stdout.write(self.style.SUCCESS(f"Eslatma yuborildi: {sent} ta"))
        else:
            self.stdout.write("Eslatma yuboriladigan navbat topilmadi.")
