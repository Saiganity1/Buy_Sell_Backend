from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework import viewsets, mixins, status
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from django.db.models import Q

from .models import Product, CartItem, Order, OrderItem, Message, Category, ProductVariant
from .serializers import (
    UserSerializer, AdminCreateUserSerializer, UserPublicSerializer,
    ProductSerializer, CartItemSerializer, OrderSerializer, MessageSerializer, CategorySerializer
)
from django.conf import settings
from django.http import JsonResponse
import os
from .permissions import IsAdmin, IsOwnerOrAdmin

User = get_user_model()


class RegisterViewSet(mixins.CreateModelMixin, viewsets.GenericViewSet):
    permission_classes = [AllowAny]
    serializer_class = UserSerializer


class AdminUserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all().order_by('id')
    serializer_class = AdminCreateUserSerializer
    permission_classes = [IsAdmin]

    @action(detail=True, methods=['get'])
    def products(self, request, pk=None):
        user = self.get_object()
        qs = Product.objects.filter(seller=user).order_by('-created_at')
        return Response(ProductSerializer(qs, many=True).data)


class ProductViewSet(viewsets.ModelViewSet):
    queryset = Product.objects.filter(available=True, archived=False).select_related('seller').order_by('-created_at')
    serializer_class = ProductSerializer
    parser_classes = (MultiPartParser, FormParser, JSONParser)

    def destroy(self, request, *args, **kwargs):
        # Soft-delete (archive) products instead of permanently deleting
        instance = self.get_object()
        instance.archived = True
        instance.available = False
        instance.save(update_fields=['archived', 'available'])
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['post'], permission_classes=[IsOwnerOrAdmin])
    def archive(self, request, pk=None):
        """Owner or admin: archive (soft-delete) a product."""
        obj = self.get_object()
        obj.archived = True
        obj.available = False
        obj.save(update_fields=['archived', 'available'])
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['post'], permission_classes=[IsOwnerOrAdmin])
    def restore(self, request, pk=None):
        """Owner or admin: restore an archived product back to available state."""
        try:
            obj = self.get_object()
            obj.archived = False
            obj.available = True
            obj.save(update_fields=['archived', 'available'])
            return Response(self.get_serializer(obj).data, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['get'], permission_classes=[IsAdmin])
    def archived(self, request):
        """Admin-only: list archived products."""
        qs = Product.objects.filter(archived=True).order_by('-created_at')
        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = self.get_serializer(page, many=True, context={'request': request})
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(qs, many=True, context={'request': request})
        return Response(serializer.data)

    def list(self, request, *args, **kwargs):
        qs = self.get_queryset()
        try:
            cnt = qs.count()
            print(f"[ProductViewSet.list] returning {cnt} products")
        except Exception:
            pass
        return super().list(request, *args, **kwargs)

    def create(self, request, *args, **kwargs):
        # Explicit create to log validation errors and ensure context is passed
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            self.perform_create(serializer)
            headers = self.get_success_headers(serializer.data)
            return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)
        # Log detailed errors to server console for troubleshooting
        print("[ProductViewSet.create] validation errors:", serializer.errors)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def perform_create(self, serializer):
        # Ensure newly created products are always available by default
        serializer.save(seller=self.request.user, available=True)

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [AllowAny()]
        if self.action in ['update', 'partial_update', 'destroy']:
            return [IsOwnerOrAdmin()]
        return super().get_permissions()

    def get_queryset(self):
        qs = super().get_queryset()
        # Allow owners or admins to include archived products in the listing using ?include_archived=true
        include_archived = str(self.request.query_params.get('include_archived') or '').lower() in ('1', 'true', 'yes')
        # If include_archived requested, only allow if user is admin; owners can include their own archived products via seller_id filter
        if include_archived:
            if getattr(self.request.user, 'is_staff', False) or getattr(self.request.user, 'role', '') == 'ADMIN':
                qs = Product.objects.all().select_related('seller').order_by('-created_at')
            else:
                seller_id = self.request.query_params.get('seller_id')
                if seller_id and str(seller_id) == str(getattr(self.request.user, 'id', '')):
                    qs = Product.objects.filter(seller_id=seller_id).select_related('seller').order_by('-created_at')
                else:
                    # not allowed to see other sellers' archived items
                    qs = qs.filter(archived=False)
        seller_id = self.request.query_params.get('seller_id')
        if seller_id:
            qs = qs.filter(seller_id=seller_id)
        q = self.request.query_params.get('q')
        if q:
            qs = qs.filter(Q(title__icontains=q) | Q(description__icontains=q))
        category_id = self.request.query_params.get('category')
        if hasattr(Product, 'category_id') and category_id:
            qs = qs.filter(category_id=category_id)
        return qs


class CartViewSet(viewsets.GenericViewSet):
    serializer_class = CartItemSerializer

    def get_queryset(self):
        return CartItem.objects.filter(user=self.request.user).select_related('product').order_by('-added_at')

    def list(self, request):
        return Response(self.serializer_class(self.get_queryset(), many=True).data)

    def create(self, request):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        product = serializer.validated_data['product']
        variant = serializer.validated_data.get('variant')
        qty = serializer.validated_data.get('quantity', 1)
        # Stock check is already done in serializer.validate; here we consolidate
        item, created = CartItem.objects.get_or_create(
            user=request.user,
            product=product,
            variant=variant,
            defaults={'quantity': qty}
        )
        if not created:
            item.quantity += qty
            item.save()
        return Response(self.serializer_class(item).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, pk=None):
        item = self.get_queryset().get(pk=pk)
        quantity = int(request.data.get('quantity', item.quantity))
        if quantity <= 0:
            item.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        item.quantity = quantity
        item.save()
        return Response(self.serializer_class(item).data)

    def destroy(self, request, pk=None):
        item = self.get_queryset().get(pk=pk)
        item.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=['post'])
    @transaction.atomic
    def checkout(self, request):
        items = list(self.get_queryset())
        if not items:
            return Response({'detail': 'Cart is empty'}, status=400)
        order = Order.objects.create(user=request.user)
        for ci in items:
            # reduce stock
            if ci.variant:
                v = ProductVariant.objects.select_for_update().get(id=ci.variant_id)
                if ci.quantity > v.stock:
                    transaction.set_rollback(True)
                    return Response({'detail': f'Not enough stock for {ci.product.title} - {v.name}'}, status=400)
                v.stock -= ci.quantity
                v.save()
                OrderItem.objects.create(order=order, product=ci.product, variant=v, quantity=ci.quantity, price=ci.product.price)
            else:
                p = Product.objects.select_for_update().get(id=ci.product_id)
                if ci.quantity > p.stock:
                    transaction.set_rollback(True)
                    return Response({'detail': f'Not enough stock for {p.title}'}, status=400)
                p.stock -= ci.quantity
                p.save()
                OrderItem.objects.create(order=order, product=p, quantity=ci.quantity, price=p.price)
        CartItem.objects.filter(user=request.user).delete()
        return Response(OrderSerializer(order).data, status=201)


class OrderViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = OrderSerializer

    def get_queryset(self):
        return Order.objects.filter(user=self.request.user).prefetch_related('items__product').order_by('-created_at')


class MessageViewSet(viewsets.GenericViewSet):
    serializer_class = MessageSerializer

    def get_queryset(self):
        user = self.request.user
        qs = Message.objects.filter(Q(sender=user) | Q(recipient=user))
        partner_id = self.request.query_params.get('partner_id')
        product_id = self.request.query_params.get('product_id')
        if partner_id:
            qs = qs.filter(
                Q(sender_id=user.id, recipient_id=partner_id) |
                Q(sender_id=partner_id, recipient_id=user.id)
            )
        if product_id:
            qs = qs.filter(product_id=product_id)
        return qs.select_related('sender', 'recipient', 'product').order_by('created_at')

    def list(self, request):
        return Response(self.serializer_class(self.get_queryset(), many=True).data)

    def create(self, request):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        msg = Message.objects.create(
            sender=request.user,
            recipient=serializer.validated_data['recipient'],
            product=serializer.validated_data.get('product'),
            content=serializer.validated_data['content'],
        )
        return Response(self.serializer_class(msg).data, status=201)


class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all().order_by('name')
    serializer_class = CategorySerializer

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [AllowAny()]
        return [IsAdmin()]


def media_list_view(request):
    """Temporary debug view: list files under MEDIA_ROOT (only for staff users)."""
    if not request.user.is_authenticated or not request.user.is_staff:
        return JsonResponse({'detail': 'unauthorized'}, status=401)
    root = getattr(settings, 'MEDIA_ROOT', None)
    if not root:
        return JsonResponse({'files': []})
    out = {}
    for dirpath, dirnames, filenames in os.walk(root):
        rel = os.path.relpath(dirpath, root)
        out[rel] = filenames
    return JsonResponse({'files': out})


def media_probe_view(request):
    """Lightweight debug endpoint: check if a specific media path exists under MEDIA_ROOT.
    Query param: name (e.g. 'products/abcd.jpg'). Returns JSON {exists: bool, path: str, url: str}
    This endpoint is intentionally permissive for debugging; remove it in production.
    """
    name = request.GET.get('name') or request.GET.get('path')
    if not name:
        return JsonResponse({'detail': 'name query parameter required'}, status=400)
    # sanitize: prevent absolute paths and traversal
    if name.startswith('/') or '..' in name:
        return JsonResponse({'detail': 'invalid name'}, status=400)
    root = getattr(settings, 'MEDIA_ROOT', None)
    if not root:
        return JsonResponse({'exists': False, 'path': None, 'url': None})
    full = os.path.join(root, name)
    exists = os.path.exists(full)
    # build a URL that would be used to serve this resource
    url = None
    try:
        # Use MEDIA_URL (may be /static/media/ in production)
        media_url = getattr(settings, 'MEDIA_URL', '/media/')
        # Ensure leading slash
        if not media_url.startswith('/'):
            media_url = '/' + media_url
        url = request.build_absolute_uri(os.path.join(media_url, name))
    except Exception:
        url = None
    return JsonResponse({'exists': bool(exists), 'path': full, 'url': url})


class SimpleTokenObtainPairSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        # Allow login with either username or email (case-insensitive for email)
        username_or_email = (attrs.get('username') or '').strip()
        # If input matches an email address, or even if it doesn't contain '@' but matches a user's email, map to that username
        try:
            user = User.objects.filter(email__iexact=username_or_email).first()
            if user:
                attrs['username'] = user.username
        except Exception:
            pass
        return super().validate(attrs)

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token['username'] = user.username
        token['role'] = user.role
        token['user_id'] = user.id
        return token


class SimpleTokenObtainPairView(TokenObtainPairView):
    permission_classes = [AllowAny]
    serializer_class = SimpleTokenObtainPairSerializer


class LogoutView(APIView):
    """Invalidate a single refresh token by blacklisting it."""
    def post(self, request):
        refresh = request.data.get('refresh')
        if not refresh:
            return Response({'detail': 'refresh token required'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            token = RefreshToken(refresh)
            token.blacklist()
        except Exception:
            return Response({'detail': 'invalid or expired token'}, status=status.HTTP_400_BAD_REQUEST)
        return Response(status=status.HTTP_205_RESET_CONTENT)


class LogoutAllView(APIView):
    """Blacklist all outstanding refresh tokens for the current user."""
    def post(self, request):
        # Requires token_blacklist app enabled
        tokens = OutstandingToken.objects.filter(user=request.user)
        for t in tokens:
            BlacklistedToken.objects.get_or_create(token=t)
        return Response(status=status.HTTP_205_RESET_CONTENT)
