import re
from decimal import Decimal
from crm.models import Customer
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

customers = graphene.List(CustomerType)

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
# Validation helpers
# ----------------------------
PHONE_REGEX = re.compile(r"^(\+\d{7,15}|\d{3}-\d{3}-\d{4})$")  # +1234567890 OR 123-456-7890


def validate_phone(phone: str | None) -> None:
    if not phone:
        return
    if not PHONE_REGEX.match(phone):
        raise ValidationError("Invalid phone format. Use +1234567890 or 123-456-7890.")


def validate_unique_email(email: str) -> None:
    try:
        validate_email(email)
    except ValidationError:
        raise ValidationError("Invalid email format.")

    if Customer.objects.filter(email__iexact=email).exists():
        raise ValidationError("Email already exists.")


# ----------------------------
# Input types
# ----------------------------
class CreateCustomerInput(graphene.InputObjectType):
    name = graphene.String(required=True)
    email = graphene.String(required=True)
    phone = graphene.String(required=False)


class BulkCustomerInput(graphene.InputObjectType):
    name = graphene.String(required=True)
    email = graphene.String(required=True)
    phone = graphene.String(required=False)


class CreateProductInput(graphene.InputObjectType):
    name = graphene.String(required=True)
    price = graphene.Decimal(required=True)
    stock = graphene.Int(required=False)


class CreateOrderInput(graphene.InputObjectType):
    customer_id = graphene.ID(required=True, name="customerId")
    product_ids = graphene.List(graphene.ID, required=True, name="productIds")
    order_date = graphene.DateTime(required=False, name="orderDate")


# ----------------------------
# Mutations
# ----------------------------
class CreateCustomer(graphene.Mutation):
    class Arguments:
        input = CreateCustomerInput(required=True)

    customer = graphene.Field(CustomerType)
    message = graphene.String(required=True)

    @staticmethod
    def mutate(root, info, input: CreateCustomerInput):
        try:
            name = input.name.strip()
            email = input.email.strip()
            phone = input.phone.strip() if input.phone else None

            if not name:
                raise ValidationError("Name is required.")
            if not email:
                raise ValidationError("Email is required.")

            validate_unique_email(email)
            validate_phone(phone)

            customer = Customer.objects.create(name=name, email=email, phone=phone)
            customer.save()
            return CreateCustomer(customer=customer, message="Customer created successfully.")

        except ValidationError as e:
            raise GraphQLError(e.messages[0] if hasattr(e, "messages") else str(e))
        except IntegrityError:
            # Handles DB uniqueness race conditions
            raise GraphQLError("Email already exists.")
        except Exception:
            raise GraphQLError("Failed to create customer. Please try again.")


class BulkCreateCustomers(graphene.Mutation):
    """
    Checkpoint expects:
      bulkCreateCustomers(input: [ ... ]) { customers { ... } errors }

    We'll return:
      customers: list of created customers
      errors: list of strings (simple + checkpoint-friendly)
    """
    class Arguments:
        input = graphene.List(BulkCustomerInput, required=True)

    customers = graphene.List(CustomerType, required=True)
    errors = graphene.List(graphene.String, required=True)

    @staticmethod
    def mutate(root, info, input):
        created = []
        errors = []

        if not input:
            return BulkCreateCustomers(customers=[], errors=["Input list cannot be empty."])

        with transaction.atomic():
            for idx, c in enumerate(input):
                sp = transaction.savepoint()
                try:
                    name = c.name.strip()
                    email = c.email.strip()
                    phone = c.phone.strip() if c.phone else None

                    if not name:
                        raise ValidationError("Name is required.")
                    if not email:
                        raise ValidationError("Email is required.")

                    validate_unique_email(email)
                    validate_phone(phone)

                    obj = Customer.objects.create(name=name, email=email, phone=phone)
                    obj.save()
                    created.append(obj)
                    transaction.savepoint_commit(sp)

                except ValidationError as e:
                    transaction.savepoint_rollback(sp)
                    msg = e.messages[0] if hasattr(e, "messages") else str(e)
                    errors.append(f"Row {idx}: {msg}")

                except IntegrityError:
                    transaction.savepoint_rollback(sp)
                    errors.append(f"Row {idx}: Email already exists.")

                except Exception:
                    transaction.savepoint_rollback(sp)
                    errors.append(f"Row {idx}: Unexpected error.")

        return BulkCreateCustomers(customers=created, errors=errors)


class CreateProduct(graphene.Mutation):
    class Arguments:
        input = CreateProductInput(required=True)

    product = graphene.Field(ProductType)

    @staticmethod
    def mutate(root, info, input: CreateProductInput):
        try:
            name = input.name.strip()
            if not name:
                raise ValidationError("Product name is required.")

            price = Decimal(str(input.price))
            if price <= 0:
                raise ValidationError("Price must be a positive number.")

            stock = 0 if input.stock is None else int(input.stock)
            if stock < 0:
                raise ValidationError("Stock cannot be negative.")

            product = Product.objects.create(name=name, price=price, stock=stock)
            product.save()
            return CreateProduct(product=product)

        except ValidationError as e:
            raise GraphQLError(e.messages[0] if hasattr(e, "messages") else str(e))
        except Exception:
            raise GraphQLError("Failed to create product. Please try again.")


class CreateOrder(graphene.Mutation):
    class Arguments:
        input = CreateOrderInput(required=True)

    order = graphene.Field(OrderType)

    @staticmethod
    def mutate(root, info, input: CreateOrderInput):
        try:
            customer_id = input.customer_id
            product_ids = input.product_ids or []
            order_date = input.order_date or timezone.now()

            if not product_ids:
                raise ValidationError("At least one product must be selected.")

            try:
                customer = Customer.objects.get(pk=customer_id)
            except Customer.DoesNotExist:
                raise ValidationError("Invalid customer ID.")

            products = list(Product.objects.filter(pk__in=product_ids))
            found_ids = {str(p.id) for p in products}
            missing = [str(pid) for pid in product_ids if str(pid) not in found_ids]
            if missing:
                raise ValidationError(f"Invalid product ID(s): {', '.join(missing)}")

            # Accurate total from DB prices (source of truth)
            total_amount = sum((p.price for p in products), Decimal("0.00"))

            with transaction.atomic():
                order = Order.objects.create(
                    customer=customer,
                    order_date=order_date,
                    total_amount=total_amount,
                )
                order.save()
                order.products.set(products)

            return CreateOrder(order=order)

        except ValidationError as e:
            raise GraphQLError(e.messages[0] if hasattr(e, "messages") else str(e))
        except Exception:
            raise GraphQLError("Failed to create order. Please try again.")


# ----------------------------
# Schema entry points for import
# ----------------------------
class Query(graphene.ObjectType):
    hello = graphene.String()

    def resolve_hello(root, info):
        return "Hello, GraphQL!"


class Mutation(graphene.ObjectType):
    create_customer = CreateCustomer.Field()
    bulk_create_customers = BulkCreateCustomers.Field()
    create_product = CreateProduct.Field()
    create_order = CreateOrder.Field()
