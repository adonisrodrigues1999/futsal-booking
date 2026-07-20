#!/usr/bin/env bash
set -euo pipefail

: "${RESOURCE_GROUP_LOCATION:=centralindia}"
: "${PG_LOCATION:=centralindia}"
: "${APP_LOCATION:=southindia}"
: "${RESOURCE_GROUP:=rg-footbook-cheap}"
: "${APP_PLAN:=asp-footbook-b1}"
: "${APP_SKU:=B1}"
: "${PG_DB:=footbook}"
: "${PG_ADMIN:=footbookadmin}"

STATE_FILE=".azure-deploy.env"

echo "Checking Azure CLI login..."
az account show --query "{subscription:name, tenant:tenantId}" --output table

echo "Registering required Azure resource providers..."
az provider register --namespace Microsoft.DBforPostgreSQL --wait
az provider register --namespace Microsoft.Web --wait

if [ -f "$STATE_FILE" ]; then
  while IFS='=' read -r key value; do
    [ -n "$key" ] || continue
    if [ -z "${!key:-}" ]; then
      export "$key=$value"
    fi
  done < "$STATE_FILE"
fi

if [ -z "${WEBAPP_NAME:-}" ]; then
  WEBAPP_NAME="footbook-$(openssl rand -hex 3)"
fi

if [ -z "${PG_SERVER:-}" ]; then
  PG_SERVER="pg-footbook-$(openssl rand -hex 3)"
fi

if [ -z "${PG_PASSWORD:-}" ] || [ -z "${DJANGO_SECRET_KEY:-}" ]; then
  echo "Set PG_PASSWORD and DJANGO_SECRET_KEY before running this script."
  exit 1
fi

{
  echo "WEBAPP_NAME=$WEBAPP_NAME"
  echo "PG_SERVER=$PG_SERVER"
  echo "RESOURCE_GROUP=$RESOURCE_GROUP"
  echo "APP_PLAN=$APP_PLAN"
  echo "RESOURCE_GROUP_LOCATION=$RESOURCE_GROUP_LOCATION"
  echo "PG_LOCATION=$PG_LOCATION"
  echo "APP_LOCATION=$APP_LOCATION"
  echo "APP_SKU=$APP_SKU"
  echo "PG_DB=$PG_DB"
  echo "PG_ADMIN=$PG_ADMIN"
} > "$STATE_FILE"

echo "Using resource group: $RESOURCE_GROUP"
echo "Using web app name: $WEBAPP_NAME"
echo "Using PostgreSQL server: $PG_SERVER"
echo "Using PostgreSQL database: $PG_DB"
echo "Using App Service location: $APP_LOCATION"

if az group show --name "$RESOURCE_GROUP" --output none 2>/dev/null; then
  echo "Resource group already exists; reusing $RESOURCE_GROUP."
else
  az group create \
    --name "$RESOURCE_GROUP" \
    --location "$RESOURCE_GROUP_LOCATION" \
    --output none
fi

if az postgres flexible-server show --resource-group "$RESOURCE_GROUP" --name "$PG_SERVER" --output none 2>/dev/null; then
  echo "PostgreSQL server already exists; reusing $PG_SERVER."
  az postgres flexible-server update \
    --resource-group "$RESOURCE_GROUP" \
    --name "$PG_SERVER" \
    --admin-password "$PG_PASSWORD" \
    --output none
else
  az postgres flexible-server create \
    --resource-group "$RESOURCE_GROUP" \
    --name "$PG_SERVER" \
    --location "$PG_LOCATION" \
    --admin-user "$PG_ADMIN" \
    --admin-password "$PG_PASSWORD" \
    --sku-name Standard_B1ms \
    --tier Burstable \
    --storage-size 32 \
    --version 16 \
    --public-access 0.0.0.0 \
    --output none
fi

if az postgres flexible-server db show --resource-group "$RESOURCE_GROUP" --server-name "$PG_SERVER" --name "$PG_DB" --output none 2>/dev/null; then
  echo "PostgreSQL database already exists; reusing $PG_DB."
else
  az postgres flexible-server db create \
    --resource-group "$RESOURCE_GROUP" \
    --server-name "$PG_SERVER" \
    --name "$PG_DB" \
    --output none
fi

az postgres flexible-server firewall-rule create \
  --resource-group "$RESOURCE_GROUP" \
  --server-name "$PG_SERVER" \
  --name AllowAzureServices \
  --start-ip-address 0.0.0.0 \
  --end-ip-address 0.0.0.0 \
  --output none

if az appservice plan show --resource-group "$RESOURCE_GROUP" --name "$APP_PLAN" --output none 2>/dev/null; then
  echo "App Service plan already exists; reusing $APP_PLAN."
else
  az appservice plan create \
    --resource-group "$RESOURCE_GROUP" \
    --name "$APP_PLAN" \
    --location "$APP_LOCATION" \
    --sku "$APP_SKU" \
    --is-linux \
    --output none
fi

if az webapp show --resource-group "$RESOURCE_GROUP" --name "$WEBAPP_NAME" --output none 2>/dev/null; then
  echo "Web app already exists; reusing $WEBAPP_NAME."
else
  az webapp create \
    --resource-group "$RESOURCE_GROUP" \
    --plan "$APP_PLAN" \
    --name "$WEBAPP_NAME" \
    --runtime "PYTHON:3.10" \
    --output none
fi

az webapp update \
  --resource-group "$RESOURCE_GROUP" \
  --name "$WEBAPP_NAME" \
  --https-only true \
  --output none

az webapp config set \
  --resource-group "$RESOURCE_GROUP" \
  --name "$WEBAPP_NAME" \
  --startup-file "python -m config.startup" \
  --output none

az webapp config appsettings set \
  --resource-group "$RESOURCE_GROUP" \
  --name "$WEBAPP_NAME" \
  --settings \
    DJANGO_DEBUG=False \
    SECRET_KEY="$DJANGO_SECRET_KEY" \
    ALLOWED_HOSTS="$WEBAPP_NAME.azurewebsites.net,.azurewebsites.net,footbook.online,www.footbook.online" \
    CSRF_TRUSTED_ORIGINS="https://$WEBAPP_NAME.azurewebsites.net,https://*.azurewebsites.net,https://footbook.online,https://www.footbook.online" \
    SESSION_COOKIE_DOMAIN=.footbook.online \
    CSRF_COOKIE_DOMAIN=.footbook.online \
    SESSION_COOKIE_SECURE=True \
    CSRF_COOKIE_SECURE=True \
    SESSION_COOKIE_SAMESITE=Lax \
    CSRF_COOKIE_SAMESITE=Lax \
    SECURE_SSL_REDIRECT=True \
    EMAIL_HOST=smtp.gmail.com \
    EMAIL_PORT=587 \
    EMAIL_USE_TLS=True \
    EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend \
    EMAIL_HOST_USER=foo.book.online.india@gmail.com \
    EMAIL_HOST_PASSWORD="<gmail-app-password>" \
    DEFAULT_FROM_EMAIL=foo.book.online.india@gmail.com \
    DB_HOST="$PG_SERVER.postgres.database.azure.com" \
    DB_NAME="$PG_DB" \
    DB_USER="$PG_ADMIN" \
    DB_PASSWORD="$PG_PASSWORD" \
    DB_PORT=5432 \
    DB_SSLMODE=require \
    SCM_DO_BUILD_DURING_DEPLOYMENT=true \
    ENABLE_ORYX_BUILD=true \
  --output none

az webapp up \
  --resource-group "$RESOURCE_GROUP" \
  --name "$WEBAPP_NAME" \
  --runtime "PYTHON:3.10" \
  --output none

echo "Deployment requested."
echo "Web app: https://$WEBAPP_NAME.azurewebsites.net"
echo "PostgreSQL server: $PG_SERVER.postgres.database.azure.com"
