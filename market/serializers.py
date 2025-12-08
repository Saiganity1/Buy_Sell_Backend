from django.contrib.auth import get_user_model
import json
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from rest_framework import serializers
from .models import Product, CartItem, Order, OrderItem, Message, Category, ProductVariant


class NullablePKRelatedField(serializers.PrimaryKeyRelatedField):
    """PrimaryKeyRelatedField that treats empty string as null."""
    def to_internal_value(self, data):
        if data in ('', None):
            return None
        return super().to_internal_value(data)


class FlexibleDecimalField(serializers.DecimalField):
    """Decimal field that accepts localized strings like '1.234,56' or '1,234.56'."""
    def to_internal_value(self, data):
        s = str(data).strip()
        # Keep only digits, dot, comma
        allowed = set('0123456789.,')
        s = ''.join(ch for ch in s if ch in allowed)
        # Remove spaces and NBSP just in case
        s = s.replace(' ', '').replace('\xa0', '')
        if ',' in s:
            if '.' in s:
                # 1.234,56 -> 1234.56
                s = s.replace('.', '').replace(',', '.')
            else:
                # 100,50 -> 100.50
                s = s.replace(',', '.')
        else:
            # Remove thousands separators if too many dots
            parts = s.split('.')
            if len(parts) > 2:
                s = ''.join(parts[:-1]) + '.' + parts[-1]
        return super().to_internal_value(s)

User = get_user_model()


class UserPublicSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'first_name', 'last_name']


class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'role', 'password']
        read_only_fields = ['role']

    def create(self, validated_data):
        password = validated_data.pop('password')
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user


class AdminCreateUserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'role', 'password']

    def create(self, validated_data):
        password = validated_data.pop('password')
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user


class ProductSerializer(serializers.ModelSerializer):
    seller = UserPublicSerializer(read_only=True)
    image = serializers.ImageField(required=False, allow_null=True)
    category = NullablePKRelatedField(queryset=Category.objects.all(), required=False, allow_null=True)
    image_url = serializers.URLField(required=False, allow_blank=True)
    price = FlexibleDecimalField(max_digits=10, decimal_places=2)
    has_variants = serializers.BooleanField(required=False)
    stock = serializers.IntegerField(required=False)
    variants = serializers.ListField(child=serializers.DictField(), required=False, write_only=True)

    class Meta:
        model = Product
        fields = ['id', 'title', 'description', 'price', 'image_url', 'image', 'category', 'created_at', 'available', 'seller', 'has_variants', 'stock', 'variants']
        read_only_fields = ['id', 'created_at', 'seller']

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get('request')
        if instance.image and hasattr(instance.image, 'url'):
            url = instance.image.url
            if request is not None:
                data['image'] = request.build_absolute_uri(url)
            else:
                data['image'] = url
        # include variants list on read
        if hasattr(instance, 'variants'):
            data['variants'] = [
                {'id': v.id, 'name': v.name, 'stock': v.stock, 'active': v.active}
                for v in instance.variants.all().order_by('name')
            ]
        return data

    def validate_price(self, value):
        # Ensure two decimal places rounding after field parsed
        try:
            return Decimal(value).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        except (InvalidOperation, ValueError, TypeError):
            raise serializers.ValidationError('A valid price is required.')

    def validate(self, attrs):
        has_variants = attrs.get('has_variants', getattr(self.instance, 'has_variants', False))
        stock = attrs.get('stock', None)
        variants = attrs.get('variants', None)
        # Accept either a JSON string of the whole list, or a list of JSON strings per variant (multipart edge-case)
        if isinstance(variants, str):
            try:
                variants = json.loads(variants)
                attrs['variants'] = variants
            except Exception:
                raise serializers.ValidationError({'variants': 'Invalid JSON for variants.'})
        elif isinstance(variants, list) and variants and all(isinstance(it, str) for it in variants):
            try:
                parsed = [json.loads(it) for it in variants]
                attrs['variants'] = parsed
                variants = parsed
            except Exception:
                raise serializers.ValidationError({'variants': 'Invalid list of JSON strings. Provide objects like {"name":"Size","stock":5}.'})
        if has_variants:
            # When variants are enabled, a variants list should be provided; product-level stock is optional
            if stock is not None and stock < 0:
                raise serializers.ValidationError({'stock': 'Stock cannot be negative.'})
            if variants is not None and not isinstance(variants, list):
                raise serializers.ValidationError({'variants': 'Must be a list of {name, stock} objects.'})
            if variants is not None:
                any_valid = False
                for it in variants:
                    if isinstance(it, dict) and (it.get('name') or '').strip():
                        any_valid = True
                        break
                if not any_valid:
                    raise serializers.ValidationError({'variants': 'Provide at least one variant with a name.'})
        else:
            # No variants: require a non-negative stock number (default 0)
            if stock is None and not self.instance:
                attrs['stock'] = 0
            elif stock is not None and stock < 0:
                raise serializers.ValidationError({'stock': 'Stock cannot be negative.'})
            # ignore variants input if provided
        return attrs

    def _write_variants(self, product, variants_data):
        if variants_data is None:
            return
        # replace strategy: clear and recreate
        ProductVariant.objects.filter(product=product).delete()
        cleaned = []
        for item in variants_data:
            name = (item.get('name') or '').strip()
            stock = int(item.get('stock') or 0)
            if not name:
                continue
            cleaned.append(ProductVariant(product=product, name=name, stock=max(0, stock)))
        if cleaned:
            ProductVariant.objects.bulk_create(cleaned)

    def create(self, validated_data):
        variants_data = validated_data.pop('variants', None)
        product = super().create(validated_data)
        if validated_data.get('has_variants'):
            self._write_variants(product, variants_data)
        return product

    def update(self, instance, validated_data):
        variants_data = validated_data.pop('variants', None)
        product = super().update(instance, validated_data)
        if validated_data.get('has_variants', instance.has_variants):
            self._write_variants(product, variants_data)
        else:
            # if variants disabled, remove any existing
            ProductVariant.objects.filter(product=product).delete()
        return product


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ['id', 'name']


class CartItemSerializer(serializers.ModelSerializer):
    product = ProductSerializer(read_only=True)
    product_id = serializers.PrimaryKeyRelatedField(queryset=Product.objects.all(), write_only=True, source='product')
    variant = serializers.SerializerMethodField(read_only=True)
    variant_id = serializers.PrimaryKeyRelatedField(queryset=ProductVariant.objects.all(), write_only=True, required=False, allow_null=True, source='variant')

    class Meta:
        model = CartItem
        fields = ['id', 'product', 'product_id', 'variant', 'variant_id', 'quantity', 'added_at']
        read_only_fields = ['id', 'added_at', 'product', 'variant']

    def get_variant(self, obj):
        if obj.variant:
            return {'id': obj.variant.id, 'name': obj.variant.name, 'stock': obj.variant.stock}
        return None

    def validate(self, attrs):
        product = attrs['product']
        variant = attrs.get('variant')
        qty = attrs.get('quantity', 1)
        if product.has_variants:
            if not variant:
                raise serializers.ValidationError({'variant_id': 'Variant is required for this product.'})
            if variant.product_id != product.id:
                raise serializers.ValidationError({'variant_id': 'Variant does not belong to this product.'})
            if qty > variant.stock:
                raise serializers.ValidationError({'quantity': 'Not enough stock for selected variant.'})
        else:
            if qty > product.stock:
                raise serializers.ValidationError({'quantity': 'Not enough stock.'})
        return attrs


class OrderItemSerializer(serializers.ModelSerializer):
    product = ProductSerializer(read_only=True)
    variant = serializers.SerializerMethodField()

    class Meta:
        model = OrderItem
        fields = ['id', 'product', 'variant', 'quantity', 'price']

    def get_variant(self, obj):
        if getattr(obj, 'variant', None):
            return {'id': obj.variant.id, 'name': obj.variant.name}
        return None


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    total_amount = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = Order
        fields = ['id', 'status', 'created_at', 'items', 'total_amount']


class MessageSerializer(serializers.ModelSerializer):
    sender = UserPublicSerializer(read_only=True)
    recipient = UserPublicSerializer(read_only=True)
    recipient_id = serializers.PrimaryKeyRelatedField(queryset=User.objects.all(), write_only=True, source='recipient')
    is_read = serializers.BooleanField(read_only=True)

    class Meta:
        model = Message
        fields = ['id', 'sender', 'recipient', 'recipient_id', 'product', 'content', 'is_read', 'created_at']
        read_only_fields = ['id', 'created_at', 'sender', 'recipient']
