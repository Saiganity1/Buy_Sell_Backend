from rest_framework.permissions import BasePermission, SAFE_METHODS


class IsAdmin(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.role == 'ADMIN')


class IsOwnerOrAdmin(BasePermission):
    def has_object_permission(self, request, view, obj):
        if request.user.is_authenticated and request.user.role == 'ADMIN':
            return True
        owner = getattr(obj, 'seller', None) or getattr(obj, 'user', None) or getattr(obj, 'owner', None)
        return owner == request.user


class ReadOnly(BasePermission):
    def has_permission(self, request, view):
        return request.method in SAFE_METHODS
