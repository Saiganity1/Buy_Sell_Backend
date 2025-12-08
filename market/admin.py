from django.contrib import admin
from django.contrib.auth import get_user_model
from .models import Product, CartItem, Order, OrderItem, Message

User = get_user_model()


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ('id', 'username', 'email', 'role', 'is_active')
    list_filter = ('role', 'is_active')
    search_fields = ('username', 'email')


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'price', 'seller', 'available', 'archived', 'created_at')
    list_filter = ('available','archived')
    search_fields = ('title', 'seller__username')
    
    def get_actions(self, request):
        actions = super().get_actions(request) or {}
        # Remove the default bulk delete action to prevent permanent removals
        if 'delete_selected' in actions:
            del actions['delete_selected']
        return actions
    
    @admin.action(description='Restore selected products')
    def restore_selected(self, request, queryset):
        queryset.update(archived=False, available=True)
        self.message_user(request, f"Restored {queryset.count()} products.")


@admin.register(CartItem)
class CartItemAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'product', 'quantity')


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'status', 'created_at', 'total_amount')
    inlines = [OrderItemInline]


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ('id', 'sender', 'recipient', 'product', 'created_at')
    search_fields = ('sender__username', 'recipient__username')
