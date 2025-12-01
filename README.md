# BuyAndSell Backend (Django + DRF)

A simple buy-and-sell backend with separate admin vs user roles, products, cart/checkout, orders, and direct messaging between users.

## Features
- Custom User with role: `ADMIN` or `USER`
- JWT authentication (access/refresh)
- Product CRUD (seller-owned) and public product listing
- Cart (add/update/remove), checkout to create an Order
- Orders history per user
- Admin endpoints to list users and view each user's selling items
- Direct messages between users (per partner and optional per product)
- CORS enabled for React Native

## Quickstart

1. Create and activate a virtualenv (Windows PowerShell):

```powershell
cd "c:\Users\Saigan\Documents\test-softwae dev\BuyAndSell\backend"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

2. Apply migrations and create a superuser:

```powershell
python manage.py migrate
python manage.py createsuperuser
```

3. Run the dev server:

```powershell
python manage.py runserver 0.0.0.0:8000
```

API base URL (default): `http://localhost:8000/api/`

## Auth
- Obtain JWT: `POST /api/auth/token/` with `{ "username": "...", "password": "..." }`
- Refresh JWT: `POST /api/auth/token/refresh/` with `{ "refresh": "..." }`
- Register user: `POST /api/register/` with `{ username, email, password, first_name?, last_name? }` (role defaults to USER)
- Admin can create admins via `POST /api/admin/users/` including `role: "ADMIN"` (requires admin token)

## Key Endpoints
- Products:
  - `GET /api/products/` list all available
  - `POST /api/products/` create (seller is the logged-in user)
  - `GET /api/products/?seller_id=<id>` list by seller
  - `GET /api/products/{id}/` retrieve
  - `PUT/PATCH/DELETE /api/products/{id}/` seller/admin only
- Cart:
  - `GET /api/cart/` view my cart
  - `POST /api/cart/` `{ product_id, quantity? }` add
  - `PATCH /api/cart/{id}/` `{ quantity }` update (<=0 deletes)
  - `DELETE /api/cart/{id}/` remove
  - `POST /api/cart/checkout/` create an order from cart and clear it
- Orders:
  - `GET /api/orders/` list my orders
  - `GET /api/orders/{id}/` get order details
- Admin Users:
  - `GET /api/admin/users/` list users (admin only)
  - `GET /api/admin/users/{id}/products/` get user's products (admin only)
- Messages (Direct Chat):
  - `GET /api/messages/?partner_id=<userId>&product_id=<optional>` list thread
  - `POST /api/messages/` `{ recipient_id, product?, content }` send message

## Configuration
Environment variables (optional):
- `DJANGO_SECRET_KEY` (default: dev key)
- `DEBUG` (default: 1)
- `ALLOWED_HOSTS` (default: `*`)

## Notes
- Default DB is SQLite for simplicity. You can switch to Postgres by updating `DATABASES` in `config/settings.py` and installing/configuring `psycopg2-binary`.
- If you plan real-time chat, add Django Channels + WebSockets. For now, REST-based messaging is implemented.
