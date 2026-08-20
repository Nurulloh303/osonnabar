from rest_framework.permissions import SAFE_METHODS, BasePermission


class IsClient(BasePermission):
    message = "Bu amal faqat mijozlar uchun."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_client)


class IsBarber(BasePermission):
    message = "Bu amal faqat ustalar uchun."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_barber)


class IsSuperAdmin(BasePermission):
    message = "Bu amal faqat super admin uchun."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_superadmin)


class IsBarberOrSuperAdmin(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and (user.is_barber or user.is_superadmin))


class ReadOnlyOrAuthenticated(BasePermission):
    """GET/HEAD/OPTIONS — hammaga ochiq, qolgani — autentifikatsiya bilan."""

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        return bool(request.user and request.user.is_authenticated)
