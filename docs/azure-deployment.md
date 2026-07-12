# Fresh Azure Deployment

This repo is configured for a low-cost Django deployment on Azure App Service with Azure Database for PostgreSQL Flexible Server.

## Cost-Sensitive Shape

Use this for the cheapest setup that still keeps PostgreSQL managed by Azure:

- App: Azure App Service on Linux, `F1` for the cheapest demo/dev setup, or `B1` if you need a more production-like app that does not sleep.
- Database: Azure Database for PostgreSQL Flexible Server, burstable `Standard_B1ms`, smallest practical storage.
- Region: use one nearby low-cost region and keep every resource in the same region. The examples use `centralindia`.
- Avoid for now: Application Gateway, Front Door, NAT Gateway, private endpoints, zone redundancy, read replicas, and autoscale.

Microsoft pricing changes by region and date. Check current prices before creating resources:

- App Service pricing: https://azure.microsoft.com/pricing/details/app-service/linux/
- PostgreSQL Flexible Server pricing: https://azure.microsoft.com/pricing/details/postgresql/flexible-server/

## Prerequisites

Install Azure CLI locally and sign in:

```bash
az login
az account set --subscription "<subscription-id-or-name>"
```

Register the Azure resource providers used by the app:

```bash
az provider register --namespace Microsoft.DBforPostgreSQL --wait
az provider register --namespace Microsoft.Web --wait
```

Generate a Django secret:

```bash
python - <<'PY'
from django.core.management.utils import get_random_secret_key
print(get_random_secret_key())
PY
```

## Create Fresh Resources

Choose globally unique names:

```bash
export LOCATION="centralindia"
export RESOURCE_GROUP="rg-footbook-cheap"
export APP_PLAN="asp-footbook-f1"
export WEBAPP_NAME="footbook-$(openssl rand -hex 3)"
export PG_SERVER="pg-footbook-$(openssl rand -hex 3)"
export PG_DB="footbook"
export PG_ADMIN="footbookadmin"
export PG_PASSWORD="<strong-password>"
export DJANGO_SECRET_KEY="<generated-django-secret>"
```

The helper script stores generated names in `.azure-deploy.env` so reruns keep targeting the same resources after a partial failure.

Create the resource group:

```bash
az group create \
  --name "$RESOURCE_GROUP" \
  --location "$LOCATION"
```

Create the PostgreSQL Flexible Server:

```bash
az postgres flexible-server create \
  --resource-group "$RESOURCE_GROUP" \
  --name "$PG_SERVER" \
  --location "$LOCATION" \
  --admin-user "$PG_ADMIN" \
  --admin-password "$PG_PASSWORD" \
  --sku-name Standard_B1ms \
  --tier Burstable \
  --storage-size 32 \
  --version 16 \
  --public-access 0.0.0.0
```

Create the application database:

```bash
az postgres flexible-server db create \
  --resource-group "$RESOURCE_GROUP" \
  --server-name "$PG_SERVER" \
  --database-name "$PG_DB"
```

Allow Azure-hosted services to reach the database:

```bash
az postgres flexible-server firewall-rule create \
  --resource-group "$RESOURCE_GROUP" \
  --name "$PG_SERVER" \
  --rule-name AllowAzureServices \
  --start-ip-address 0.0.0.0 \
  --end-ip-address 0.0.0.0
```

Create the Linux App Service plan. For the absolute cheapest demo setup, use `F1`. For a small production setup, change `F1` to `B1`.

```bash
az appservice plan create \
  --resource-group "$RESOURCE_GROUP" \
  --name "$APP_PLAN" \
  --location "$LOCATION" \
  --sku F1 \
  --is-linux
```

Create the Django web app:

```bash
az webapp create \
  --resource-group "$RESOURCE_GROUP" \
  --plan "$APP_PLAN" \
  --name "$WEBAPP_NAME" \
  --runtime "PYTHON:3.10"
```

Set the startup command:

```bash
az webapp config set \
  --resource-group "$RESOURCE_GROUP" \
  --name "$WEBAPP_NAME" \
  --startup-file "python -m config.startup"
```

Set production app settings:

```bash
az webapp config appsettings set \
  --resource-group "$RESOURCE_GROUP" \
  --name "$WEBAPP_NAME" \
  --settings \
    DJANGO_DEBUG=False \
    SECRET_KEY="$DJANGO_SECRET_KEY" \
    ALLOWED_HOSTS="$WEBAPP_NAME.azurewebsites.net,.azurewebsites.net" \
    CSRF_TRUSTED_ORIGINS="https://$WEBAPP_NAME.azurewebsites.net,https://*.azurewebsites.net" \
    EMAIL_HOST=smtp.gmail.com \
    EMAIL_PORT=587 \
    EMAIL_USE_TLS=True \
    EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend \
    EMAIL_HOST_USER=foo.book.online.india@gmail.com \
    EMAIL_HOST_PASSWORD="<gmail-app-password>" \
    EMAIL_SENDER_NAME=FootBook \
    EMAIL_SENDER_ADDRESS=foo.book.online.india@gmail.com \
    EMAIL_SUBJECT_PREFIX="[FootBook] " \
    DEFAULT_FROM_EMAIL="FootBook <foo.book.online.india@gmail.com>" \
    DB_CONN_MAX_AGE=60 \
    PREGENERATE_FUTURE_SLOTS=False \
    DB_HOST="$PG_SERVER.postgres.database.azure.com" \
    DB_NAME="$PG_DB" \
    DB_USER="$PG_ADMIN" \
    DB_PASSWORD="$PG_PASSWORD" \
    DB_PORT=5432 \
    DB_SSLMODE=require \
    SCM_DO_BUILD_DURING_DEPLOYMENT=true \
    ENABLE_ORYX_BUILD=true
```

Add email and payment secrets only after rotating any exposed old credentials:

```bash
az webapp config appsettings set \
  --resource-group "$RESOURCE_GROUP" \
  --name "$WEBAPP_NAME" \
  --settings \
    EMAIL_HOST_USER="foo.book.online.india@gmail.com" \
    EMAIL_HOST_PASSWORD="<gmail-app-password>" \
    EMAIL_SENDER_NAME="FootBook" \
    EMAIL_SENDER_ADDRESS="foo.book.online.india@gmail.com" \
    EMAIL_SUBJECT_PREFIX="[FootBook] " \
    DEFAULT_FROM_EMAIL="FootBook <foo.book.online.india@gmail.com>" \
    DB_CONN_MAX_AGE=60 \
    PREGENERATE_FUTURE_SLOTS=False \
    EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend" \
    RAZORPAY_KEY_ID="<razorpay-key-id>" \
    RAZORPAY_KEY_SECRET="<razorpay-key-secret>" \
    RAZORPAY_WEBHOOK_SECRET="<razorpay-webhook-secret>"
```

Deploy from this repo:

```bash
az webapp up \
  --resource-group "$RESOURCE_GROUP" \
  --name "$WEBAPP_NAME" \
  --runtime "PYTHON:3.10"
```

Open the site:

```bash
az webapp browse \
  --resource-group "$RESOURCE_GROUP" \
  --name "$WEBAPP_NAME"
```

## Create Admin User

Use SSH from the Azure portal or run a one-off command:

```bash
az webapp ssh \
  --resource-group "$RESOURCE_GROUP" \
  --name "$WEBAPP_NAME"
```

Inside the app container:

```bash
python manage.py createsuperuser
```

## GitHub Actions Deployment

The workflow `.github/workflows/main_futbook.yml` expects these repository variables/secrets:

- Variable: `AZURE_WEBAPP_NAME`
- Secret: `AZURE_CLIENT_ID`
- Secret: `AZURE_TENANT_ID`
- Secret: `AZURE_SUBSCRIPTION_ID`

Use Azure federated credentials for GitHub Actions OIDC, then trigger the workflow manually or push to `main`.

## Cost Controls

For non-production periods, stop PostgreSQL to avoid compute charges:

```bash
az postgres flexible-server stop \
  --resource-group "$RESOURCE_GROUP" \
  --name "$PG_SERVER"
```

Start it again before using the app:

```bash
az postgres flexible-server start \
  --resource-group "$RESOURCE_GROUP" \
  --name "$PG_SERVER"
```

Delete everything if you are done testing:

```bash
az group delete \
  --name "$RESOURCE_GROUP"
```

## Important Security Cleanup

Old database, Gmail, Razorpay, and Stripe credentials were previously committed in settings. Rotate those credentials before deploying again, because removing them from code does not make previously exposed values safe.
