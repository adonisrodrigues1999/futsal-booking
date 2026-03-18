diff --git a//Users/adonisrodrigues/footbook/futsal-booking/README.md b//Users/adonisrodrigues/footbook/futsal-booking/README.md
new file mode 100644
--- /dev/null
+++ b//Users/adonisrodrigues/footbook/futsal-booking/README.md
@@ -0,0 +1,270 @@
+# FootBook
+
+FootBook is a Django-based futsal ground booking platform for three user roles:
+
+- Customers can register, verify email, browse grounds, book slots, pay online, cancel, and reschedule.
+- Ground owners can manage bookings, create walk-in/manual bookings, track collections, record expenses, and monitor business performance.
+- Admins can create owners and grounds, review platform metrics, generate invoices, export CSV reports, and manage settlements.
+
+The application is built as a server-rendered Django app with PostgreSQL, custom authentication, Razorpay payment support for customer bookings, optional Stripe-based invoice payment support, and WhiteNoise-based static asset serving.
+
+## Product Capabilities
+
+### Customer flow
+
+- Self-registration with email verification
+- Login using either email or phone number
+- Password reset by email
+- Ground listing and day-wise slot browsing
+- Real-time slot status checks
+- Online checkout through Razorpay
+- Full-payment or partial advance payment (`₹99`) flows
+- Booking history view
+- Customer-initiated cancellation
+- Customer-initiated rescheduling when the slot is at least 4 hours away
+
+### Ground owner flow
+
+- Owner dashboard with revenue, collection, due, and booking-source splits
+- Manual booking for walk-in customers
+- Marking due bookings as paid at ground
+- Owner-side cancellation and rescheduling
+- Expense tracking by category
+- Ground-level performance reporting
+- Booking reminder emails
+
+### Admin flow
+
+- Admin dashboard for owner, ground, and customer management
+- Ground-owner creation
+- Ground creation with initial slot generation
+- Monthly booking and settlement summaries
+- Invoice generation by ground and date range
+- CSV export for invoices and bookings
+- Invoice paid/unpaid toggles
+- Optional Stripe checkout flow for invoice payment
+
+## Tech Stack
+
+- Python 3
+- Django 4.2
+- PostgreSQL in the main settings
+- SQLite in `config.test_settings`
+- Razorpay for customer payments
+- Stripe hooks in invoice settlement flows
+- WhiteNoise for static files
+- Gunicorn for deployment
+
+## Architecture
+
+The project is organized into focused Django apps:
+
+- `accounts`: custom user model, auth, registration, verification, password reset, admin/owner/customer dashboards
+- `grounds`: futsal ground data and image sync tooling
+- `bookings`: slot generation, booking flows, payments, rescheduling, cancellations, invoices, expenses, reminders
+- `dashboard`: placeholder app, currently most dashboard logic lives elsewhere
+- `notifications`: placeholder app, latest booking notifications are currently served from `bookings`
+
+Core domain models include:
+
+- `accounts.User`: custom auth model with `admin`, `owner`, and `customer` roles
+- `grounds.Ground`: venue metadata, pricing, schedule, owner mapping
+- `bookings.Slot`: hourly inventory per ground/date/time
+- `bookings.Booking`: booking and payment state
+- `bookings.OwnerExpense`: owner-side operating expenses
+- `bookings.GroundInvoice`: admin-generated invoice records
+- `bookings.ActivityLog`: operational event log
+- `bookings.EmailVerification`: registration verification token store
+
+## Booking and Payment Logic
+
+Slots are generated in hourly increments based on each ground's operating window. The system supports standard same-day ranges and cross-midnight schedules.
+
+Online bookings go through Razorpay:
+
+- The server creates a Razorpay order for a slot.
+- The client completes checkout.
+- The server verifies payment signature and amount.
+- The slot is locked with a database transaction.
+- A booking is created and the slot is marked booked.
+
+Payment modes currently supported:
+
+- `FULL`: full amount collected online
+- `PARTIAL_99`: `₹99` collected online and the rest tracked as due at the ground
+
+Manual owner bookings bypass online checkout and create bookings directly for walk-in customers.
+
+## Project Structure
+
+```text
+.
+├── accounts/
+├── bookings/
+├── config/
+├── dashboard/
+├── grounds/
+├── notifications/
+├── scripts/
+├── static/
+├── templates/
+├── manage.py
+└── requirements.txt
+```
+
+Useful paths:
+
+- `config/settings.py`: main Django settings
+- `config/test_settings.py`: isolated test/build configuration
+- `bookings/views.py`: primary business logic and booking flows
+- `bookings/slot_generation.py`: slot creation logic
+- `scripts/test_unit.sh`: unit/integration test entrypoint
+- `scripts/test_e2e_build.sh`: build-safety checks for CI
+- `scripts/test_fraud.sh`: targeted booking/fraud-flow checks
+
+## Local Setup
+
+### 1. Clone and enter the project
+
+```bash
+git clone <your-repo-url>
+cd futsal-booking
+```
+
+### 2. Create a virtual environment
+
+```bash
+python -m venv venv
+source venv/bin/activate
+```
+
+### 3. Install dependencies
+
+```bash
+pip install -r requirements.txt
+```
+
+### 4. Configure settings
+
+The current repository stores database, email, and payment credentials directly in [`config/settings.py`](/Users/adonisrodrigues/footbook/futsal-booking/config/settings.py). Before publishing this repository or running it outside your own environment:
+
+1. Rotate any exposed credentials immediately.
+2. Move secrets to environment variables.
+3. Replace `DEBUG = True` and permissive `ALLOWED_HOSTS`.
+
+Recommended values to externalize:
+
+- `SECRET_KEY`
+- database host, name, user, password, port
+- `EMAIL_HOST_USER`
+- `EMAIL_HOST_PASSWORD`
+- `DEFAULT_FROM_EMAIL`
+- `RAZORPAY_KEY_ID`
+- `RAZORPAY_KEY_SECRET`
+- `RAZORPAY_WEBHOOK_SECRET`
+- `STRIPE_SECRET_KEY`
+- `STRIPE_PUBLIC_KEY`
+- `STRIPE_WEBHOOK_SECRET`
+
+### 5. Apply migrations
+
+```bash
+python manage.py migrate
+```
+
+### 6. Create an admin user
+
+Use Django shell or the included command style already present in the repo. If you want the standard Django command:
+
+```bash
+python manage.py createsuperuser
+```
+
+Note: the project uses a custom user model with role-based behavior. You may also want to create role-specific users for admin, owner, and customer testing.
+
+### 7. Run the development server
+
+```bash
+python manage.py runserver
+```
+
+Open `http://127.0.0.1:8000/`.
+
+## Test Commands
+
+Run the main test suite:
+
+```bash
+bash scripts/test_unit.sh
+```
+
+Run build-style checks used for CI:
+
+```bash
+bash scripts/test_e2e_build.sh
+```
+
+Run targeted fraud/payment-flow checks:
+
+```bash
+bash scripts/test_fraud.sh
+```
+
+The repository uses [`config/test_settings.py`](/Users/adonisrodrigues/footbook/futsal-booking/config/test_settings.py), which switches tests to SQLite and relaxes staticfiles strictness for repeatable local and CI execution.
+
+## Management Commands
+
+Available project-specific commands include:
+
+```bash
+python manage.py create_admin
+python manage.py populate_data
+python manage.py sync_ground_images
+python manage.py clear_bookings
+python manage.py send_reminders
+```
+
+What they are for:
+
+- `sync_ground_images`: copies files from `groundsimages/` into static assets and updates `Ground.image`
+- `send_reminders`: sends reminder emails roughly 45 minutes before booked slots
+- `clear_bookings`: utility cleanup command for booking data
+- `populate_data`: seed/demo data helper
+- `create_admin`: custom admin bootstrap command
+
+## Deployment Notes
+
+The project already includes several production-oriented pieces:
+
+- `gunicorn` in dependencies
+- WhiteNoise static serving
+- secure cookie settings for HTTPS deployments
+- Azure-oriented trusted origin configuration in settings
+
+Before production deployment, you should still address:
+
+- secret management via environment variables
+- `DEBUG = False`
+- restricted `ALLOWED_HOSTS`
+- proper logging and error reporting
+- secure email credentials
+- webhook secret configuration
+- database migration workflow
+- static file collection with `python manage.py collectstatic`
+
+## Known Gaps and Cleanup Areas
+
+This repository is functional, but a few areas are worth cleaning up before sharing publicly or scaling further:
+
+- `config/settings.py` currently contains sensitive values and should be refactored immediately
+- `bookings/services.py` references models and fields that no longer match the current booking schema, so it appears stale
+- `dashboard` and `notifications` apps contain little or no active model/view logic
+- most business logic is concentrated in [`bookings/views.py`](/Users/adonisrodrigues/footbook/futsal-booking/bookings/views.py), which would benefit from service-layer extraction
+
+## Suggested GitHub Description
+
+`FootBook is a Django-based futsal ground booking platform with customer booking, owner operations, admin invoicing, Razorpay payments, and role-based dashboards.`
+
+## License
+
+Add a project license before publishing publicly. If this is private/internal software, state that explicitly in the repository settings or replace this section with your preferred license text.
