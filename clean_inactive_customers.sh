#!/bin/bash

# Navigate to project root (adjust if needed)
PROJECT_ROOT="/c/Users/CMS-008/my_project/alx_backend_graphql_crm"

# Run Django shell command to delete inactive customers
DELETED_COUNT=$(python3 "$PROJECT_ROOT/manage.py" shell -c "
from datetime import timedelta
from django.utils import timezone
from crm.models import Customer, Order

one_year_ago = timezone.now() - timedelta(days=365)

inactive_customers = Customer.objects.exclude(
    id__in=Order.objects.filter(order_date__gte=one_year_ago).values_list('customer_id', flat=True)
)

count = inactive_customers.count()
inactive_customers.delete()
print(count)
")

# Log result with timestamp
echo \"$(date '+%Y-%m-%d %H:%M:%S') - Deleted $DELETED_COUNT inactive customers\" >> /tmp/customer_cleanup_crontab.txt
