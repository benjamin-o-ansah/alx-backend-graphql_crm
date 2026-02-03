import re
from decimal import Decimal
from typing import List, Optional

import graphene
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, transaction
from django.utils import timezone
from graphene_django import DjangoObjectType
from graphql import GraphQLError

from crm.models import Customer, Product, Order


# ----------------------------
# GraphQL Types
# ----------------------------
class CustomerType(DjangoObjectType):
    class Meta:
        model = Customer
        fields = ("id", "name", "email", "phone")


class ProductType(DjangoObjectType):
    class Meta:
        model = Product
        fields = ("id", "name", "price", "stock")


class OrderType(DjangoObjectType):
    class Meta:
        model = Order
        fields = ("id", "customer", "products", "order_date", "total_amount")


# ----------------------------
# Helpers: Validation
# ----------------------------
PHONE_REGEX = re.compile(r"^(\+\d{7,15}|\d{3}-\d{3}-\d{4})$")  # +1234567890 OR 123-456-7890


def _validate_phone(phone: Optional[str]) -> None:
    if phone is None or phone == "":
        return
    if not PHONE_REGEX.match(phone):
        raise ValidationError("Invalid phone format. Use +1234567890 or 123-456-7890.")


def _validate_unique_email(email: str) -> None:
    # Validate basic email format first (clean error message)
    try:
        validate_email(email)
    except ValidationError:
        raise ValidationError("Invalid email format.")

    # Enforce uniqueness at app level (still keep DB unique=True ideally)
    if Customer.objects.filter(email__iexact=email).exists():
        raise ValidationError("Email already exists.")


# ----------------------------
# Inputs / Error Types
# ----------------------------
class CustomerInput(graphene.InputObjectType):
    name = graphene.String(required=True)
    email = graphene.String(required=True)
    phone = graphene.String(required=False)


class BulkCustomerErrorType(graphene.ObjectType):
    index = graphene.Int(required=True)          # position in the input list
    email = graphene.String()                    # may be null if missing/invalid
    message = graphene.String(required=True)


# ----------------------------
# Mutations
# ----------------------------
class CreateCustomer(graphene.Mutation):
    class Arguments:
        name = graphene.String(required=True)
        email = graphene.String(required=True)
        phone = graphene.String(required=False)

    customer = graphene.Field(CustomerType)
    message = graphene.String()

    @staticmethod
    def mutate(root, info, name: str, email: str, phone: Optional[str] = None):
        try:
            _validate_unique_email(email)
            _validate_phone(phone)

            customer = Customer(name=name.strip(), email=email.strip(), phone=(phone.strip() if phone else None))
            customer.save()
            return CreateCustomer(customer=customer, message="Customer created successfully.")
        except ValidationError as e:
            # User-friendly GraphQL error
            raise GraphQLError(str(e.messages[0] if hasattr(e, "messages") else e))
        except IntegrityError:
            # In case the DB unique constraint triggers (race conditions)
            raise GraphQLError("Email already exists.")
        except Exception:
            raise GraphQLError("Failed to create customer. Please try again.")


class BulkCreateCustomers(graphene.Mutation):
    """
    Partial success supported:
    - Valid records are created
    - Invalid records are skipped
    - Returns created_customers + errors (per item)
    - Uses one outer transaction + per-item savepoints
    """
    class Arguments:
        customers = graphene.List(CustomerInput, required=True)

    created_customers = graphene.List(CustomerType, required=True)
    errors = graphene.List(BulkCustomerErrorType, required=True)
    message = graphene.String()

    @staticmethod
    def mutate(root, info, customers: List[CustomerInput]):
        created: List[Customer] = []
        errors: List[BulkCustomerErrorType] = []

        if not customers:
            return BulkCreateCustomers(
                created_customers=[],
                errors=[BulkCustomerErrorType(index=0, email=None, message="Customer list cannot be empty.")],
                message="No customers created.",
            )

        with transaction.atomic():
            for idx, c in enumerate(customers):
                sp_id = transaction.savepoint()
                try:
                    name = (c.name or "").strip()
                    email = (c.email or "").strip()
                    phone = (c.phone or "").strip() if c.phone else None

                    if not name:
                        raise ValidationError("Name is required.")
                    if not email:
                        raise ValidationError("Email is required.")

                    _validate_unique_email(email)
                    _validate_phone(phone)

                    obj = Customer(name=name, email=email, phone=phone)
                    obj.save()
                    created.append(obj)

                    transaction.savepoint_commit(sp_id)
                except ValidationError as e:
                    transaction.savepoint_rollback(sp_id)
                    msg = str(e.messages[0] if hasattr(e, "messages") else e)
                    errors.append(BulkCustomerErrorType(index=idx, email=getattr(c, "email", None), message=msg))
                except IntegrityError:
                    transaction.savepoint_rollback(sp_id)
                    errors.append(BulkCustomerErrorType(index=idx, email=getattr(c, "email", None), message="Email already exists."))
                except Exception:
                    transaction.savepoint_rollback(sp_id)
                    errors.append(BulkCustomerErrorType(index=idx, email=getattr(c, "email", None), message="Unexpected error creating this customer."))

        msg = "Customers created successfully." if created else "No customers created."
        return BulkCreateCustomers(created_customers=created, errors=errors, message=msg)


class CreateProduct(graphene.Mutation):
    class Arguments:
        name = graphene.String(required=True)
        price = graphene.Decimal(required=True)
        stock = graphene.Int(required=False)

    product = graphene.Field(ProductType)

    @staticmethod
    def mutate(root, info, name: str, price, stock: Optional[int] = 0):
        try:
            name = name.strip()
            if not name:
                raise ValidationError("Product name is required.")

            # Graphene Decimal arrives as Decimal-compatible; normalize:
            price = Decimal(str(price))
            if price <= 0:
                raise ValidationError("Price must be a positive number.")

            if stock is None:
                stock = 0
            if stock < 0:
                raise ValidationError("Stock cannot be negative.")

            product = Product(name=name, price=price, stock=stock)
            product.save()
            return CreateProduct(product=product)
        except ValidationError as e:
            raise GraphQLError(str(e.messages[0] if hasattr(e, "messages") else e))
        except Exception:
            raise GraphQLError("Failed to create product. Please try again.")


class CreateOrder(graphene.Mutation):
    class Arguments:
        customer_id = graphene.ID(required=True)
        product_ids = graphene.List(graphene.ID, required=True)
        order_date = graphene.DateTime(required=False)

    order = graphene.Field(OrderType)

    @staticmethod
    def mutate(root, info, customer_id, product_ids: List, order_date=None):
        try:
            if not product_ids or len(product_ids) == 0:
                raise ValidationError("At least one product must be selected.")

            # Validate customer
            try:
                customer = Customer.objects.get(pk=customer_id)
            except Customer.DoesNotExist:
                raise ValidationError("Invalid customer ID.")

            # Validate products (ensure all exist)
            products = list(Product.objects.filter(pk__in=product_ids))
            found_ids = {str(p.id) for p in products}
            missing = [str(pid) for pid in product_ids if str(pid) not in found_ids]
            if missing:
                # user-friendly message showing the first missing (or list them)
                raise ValidationError(f"Invalid product ID(s): {', '.join(missing)}")

            # Determine date
            if order_date is None:
                order_date = timezone.now()

            # Compute total_amount from DB product prices (source-of-truth)
            total_amount = sum((p.price for p in products), Decimal("0.00"))

            with transaction.atomic():
                order = Order.objects.create(
                    customer=customer,
                    order_date=order_date,
                    total_amount=total_amount,
                )
                order.products.set(products)

            return CreateOrder(order=order)

        except ValidationError as e:
            raise GraphQLError(str(e.messages[0] if hasattr(e, "messages") else e))
        except Exception:
            raise GraphQLError("Failed to create order. Please try again.")


# ----------------------------
# Query + Mutation Root for crm
# ----------------------------
class CRMQuery(graphene.ObjectType):
    hello = graphene.String()

    def resolve_hello(root, info):
        return "Hello, GraphQL!"


class CRMMutation(graphene.ObjectType):
    create_customer = CreateCustomer.Field()
    bulk_create_customers = BulkCreateCustomers.Field()
    create_product = CreateProduct.Field()
    create_order = CreateOrder.Field()
