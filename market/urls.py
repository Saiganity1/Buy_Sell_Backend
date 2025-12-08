from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView

from .views import (
    RegisterViewSet,
    AdminUserViewSet,
    ProductViewSet,
    CartViewSet,
    OrderViewSet,
    MessageViewSet,
    CategoryViewSet,
    SimpleTokenObtainPairView,
    LogoutView,
    LogoutAllView,
    media_list_view,
)

router = DefaultRouter()
router.register(r'register', RegisterViewSet, basename='register')
router.register(r'admin/users', AdminUserViewSet, basename='admin-users')
router.register(r'products', ProductViewSet, basename='products')
router.register(r'cart', CartViewSet, basename='cart')
router.register(r'orders', OrderViewSet, basename='orders')
router.register(r'messages', MessageViewSet, basename='messages')
router.register(r'categories', CategoryViewSet, basename='categories')

urlpatterns = [
    path('_media_list/', media_list_view, name='media_list'),
    path('auth/token/', SimpleTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('auth/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('auth/logout/', LogoutView.as_view(), name='auth_logout'),
    path('auth/logout-all/', LogoutAllView.as_view(), name='auth_logout_all'),
    path('', include(router.urls)),
]
