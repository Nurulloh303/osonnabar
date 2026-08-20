from django.contrib.auth.base_user import BaseUserManager


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, phone=None, email=None, password=None, **extra):
        if not phone and not email:
            raise ValueError("Telefon raqam yoki email ko'rsatilishi shart.")
        email = self.normalize_email(email) if email else None
        user = self.model(phone=phone or None, email=email, **extra)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_user(self, phone=None, email=None, password=None, **extra):
        extra.setdefault("role", self.model.Role.CLIENT)
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create_user(phone, email, password, **extra)

    def create_superuser(self, phone=None, email=None, password=None, **extra):
        extra.setdefault("role", self.model.Role.SUPERADMIN)
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        extra.setdefault("is_phone_verified", True)
        if extra.get("is_staff") is not True:
            raise ValueError("Superuser is_staff=True bo'lishi kerak.")
        return self._create_user(phone, email, password, **extra)
