from rest_framework import permissions


class IsStoreAdmin(permissions.BasePermission):
    """Allow staff users and users with the ADMIN business role."""

    def has_permission(self, request, view):
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and (getattr(user, 'role', None) == 'ADMIN' or user.is_staff)
        )
