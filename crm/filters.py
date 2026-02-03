import django_filters
from django.db.models import QuerySet

from crm.models import Customer, Product, Order


class CustomerFilter(django_filters.FilterSet):
    # Case-insensitive partial matches
    name = django_filters.CharFilter(field_name="name", lookup_expr="icontains")
    email = django_filters.CharFilter(field_name="email", lookup_expr="icontains")

    # Date range filters
    created_at__gte = django_filters.DateFilter(field_name="created_at", lookup_expr="gte")
    created_at__lte = django_filters.DateFilter(field_name="created_at", lookup_expr="lte")

    # Challenge: phone pattern filter (e.g., starts with +1)
    phone_pattern = django_filters.CharFilter(method="filter_phone_pattern")

    def filter_phone_pattern(self, queryset: QuerySet, name: str, value: str) -> QuerySet:
        # Example value: "+1"
        if not value:
            return queryset
        return queryset.filter(phone__startswith=value)

    class Meta:
        model = Customer
        fields = ["name", "email", "created_at__gte", "created_at__lte", "phone_pattern"]


class ProductFilter(django_filters.FilterSet):
    name = django_filters.CharFilter(field_name="name", lookup_expr="icontains")

    price__gte = django_filters.NumberFilter(field_name="price", lookup_expr="gte")
    price__lte = django_filters.NumberFilter(field_name="price", lookup_expr="lte")

    stock__gte = django_filters.NumberFilter(field_name="stock", lookup_expr="gte")
    stock__lte = django_filters.NumberFilter(field_name="stock", lookup_expr="lte")

    # Think: low stock (e.g., stock < 10) - optional helper
    low_stock = django_filters.BooleanFilter(method="filter_low_stock")

    def filter_low_stock(self, queryset: QuerySet, name: str, value: bool) -> QuerySet:
        if value:
            return queryset.filter(stock__lt=10)
        return queryset

    class Meta:
        model = Product
        fields = ["name", "price__gte", "price__lte", "stock__gte", "stock__lte", "low_stock"]


class OrderFilter(django_filters.FilterSet):
    total_amount__gte = django_filters.NumberFilter(field_name="total_amount", lookup_expr="gte")
    total_amount__lte = django_filters.NumberFilter(field_name="total_amount", lookup_expr="lte")

    order_date__gte = django_filters.DateTimeFilter(field_name="order_date", lookup_expr="gte")
    order_date__lte = django_filters.DateTimeFilter(field_name="order_date", lookup_expr="lte")

    # Related field lookups
    customer_name = django_filters.CharFilter(field_name="customer__name", lookup_expr="icontains")
    product_name = django_filters.CharFilter(field_name="products__name", lookup_expr="icontains")

    # Challenge: orders that include a specific product ID
    product_id = django_filters.NumberFilter(field_name="products__id", lookup_expr="exact")

    class Meta:
        model = Order
        fields = [
            "total_amount__gte",
            "total_amount__lte",
            "order_date__gte",
            "order_date__lte",
            "customer_name",
            "product_name",
            "product_id",
        ]
