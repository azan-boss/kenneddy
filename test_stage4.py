import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

import asyncio
import json
import requests
import websockets
from decimal import Decimal
from django.contrib.auth.models import User
from accounts.models import Address, Profile, Role
from menu.models import Dish, DishSize, MenuCategory
from orders.models import Order, OrderItem

BASE_URL = "http://127.0.0.1:8000"
WS_URL = "ws://127.0.0.1:8000"

def get_token(username, password="pass12345"):
    res = requests.post(f"{BASE_URL}/api/auth/login/", json={"username": username, "password": password})
    if res.status_code != 200:
        return None
    return res.json()["access"]

def auth_header(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

def run_tests():
    print("==================================================")
    print("STARTING STAGE 4 VERIFICATION TEST SUITE")
    print("==================================================")

    # ----------------------------------------------------
    # 1. Safe role selection at signup & Rider Approval
    # ----------------------------------------------------
    print("\n--- TEST 1: Signup with requested_role='kitchen' or 'admin' -> expect 400 & 0 rows created ---")
    bad_signup_payload = {
        "username": "hacker_chef",
        "email": "chef@hacker.com",
        "password": "strongpassword123",
        "requested_role": "kitchen",
    }
    res = requests.post(f"{BASE_URL}/api/auth/signup/", json=bad_signup_payload)
    print(f"Kitchen signup status code: {res.status_code}, errors: {res.text}")
    assert res.status_code == 400, f"Expected 400 for kitchen signup, got {res.status_code}"
    assert User.objects.filter(username="hacker_chef").count() == 0, "Security error: User row created on rejected signup!"
    print("PASS: Kitchen self-signup rejected, 0 DB rows created.")

    bad_admin_signup = {
        "username": "hacker_admin",
        "email": "admin@hacker.com",
        "password": "strongpassword123",
        "requested_role": "admin",
    }
    res = requests.post(f"{BASE_URL}/api/auth/signup/", json=bad_admin_signup)
    assert res.status_code == 400, f"Expected 400 for admin signup, got {res.status_code}"
    assert User.objects.filter(username="hacker_admin").count() == 0, "Security error: Admin row created on rejected signup!"
    print("PASS: Admin self-signup rejected, 0 DB rows created.")

    print("\n--- TEST 2: Signup with requested_role='customer' -> is_active=True, login works immediately ---")
    User.objects.filter(username="test_customer_4").delete()
    res = requests.post(f"{BASE_URL}/api/auth/signup/", json={
        "username": "test_customer_4",
        "email": "cust4@test.com",
        "password": "securepassword123",
        "requested_role": "customer",
    })
    assert res.status_code == 201, f"Customer signup failed: {res.text}"
    token_cust4 = get_token("test_customer_4", "securepassword123")
    assert token_cust4 is not None, "Login failed for newly created active customer"
    cust4_user = User.objects.get(username="test_customer_4")
    assert cust4_user.is_active is True
    assert cust4_user.profile.role == Role.CUSTOMER
    print(f"PASS: Customer signed up, active=True, login succeeded.")

    print("\n--- TEST 3: Signup with requested_role='rider' -> is_active=False, pending approval ---")
    User.objects.filter(username="pending_rider_4").delete()
    res = requests.post(f"{BASE_URL}/api/auth/signup/", json={
        "username": "pending_rider_4",
        "email": "rider4@test.com",
        "password": "securepassword123",
        "requested_role": "rider",
    })
    assert res.status_code == 201, f"Rider signup failed: {res.text}"
    data = res.json()
    assert data.get("status") == "pending_approval", f"Expected pending_approval status, got {data}"
    rider4_user = User.objects.get(username="pending_rider_4")
    assert rider4_user.is_active is False
    assert rider4_user.profile.role == Role.RIDER
    print("PASS: Rider signed up with is_active=False & pending_approval message.")

    # Try login before approval -> expect failure
    token_rider_unapproved = get_token("pending_rider_4", "securepassword123")
    assert token_rider_unapproved is None, "Security error: Unapproved inactive rider was able to log in!"
    print("PASS: Inactive rider login blocked as expected.")

    # Admin approves rider
    admin_user, _ = User.objects.get_or_create(username="admin_stage4", defaults={"email": "admin4@test.com"})
    admin_user.set_password("securepassword123")
    admin_user.is_staff = True
    admin_user.save()
    admin_prof, _ = Profile.objects.get_or_create(user=admin_user)
    admin_prof.role = Role.ADMIN
    admin_prof.save()
    token_admin = get_token("admin_stage4", "securepassword123")

    approve_res = requests.post(
        f"{BASE_URL}/api/admin/riders/{rider4_user.id}/approve/",
        headers=auth_header(token_admin)
    )
    assert approve_res.status_code == 200, f"Approval failed: {approve_res.text}"
    rider4_user.refresh_from_db()
    assert rider4_user.is_active is True
    print("PASS: Admin successfully approved rider.")

    # Login after approval -> expect success
    token_rider_approved = get_token("pending_rider_4", "securepassword123")
    assert token_rider_approved is not None, "Login failed for approved rider"
    print("PASS: Approved rider can now log in successfully.")

    # ----------------------------------------------------
    # 2. Multi-Address Support & Isolation
    # ----------------------------------------------------
    print("\n--- TEST 4: Address CRUD & Validation ---")
    # Missing lat/lng -> 400
    res = requests.post(f"{BASE_URL}/api/addresses/", json={
        "label": "Home",
        "name": "Customer 4",
        "phone": "03001234567",
        "street": "123 Main St",
        "area": "Gulberg III",
        "city": "Lahore",
    }, headers=auth_header(token_cust4))
    assert res.status_code == 400, f"Expected 400 for missing coords, got {res.status_code}"
    print("PASS: Address creation without lat/lng correctly returns 400.")

    # Valid Address 1 (Home)
    res_addr1 = requests.post(f"{BASE_URL}/api/addresses/", json={
        "label": "Home",
        "name": "Customer 4",
        "phone": "03001234567",
        "street": "123 Main St",
        "area": "Gulberg III",
        "city": "Lahore",
        "notes": "Gate 2",
        "lat": 31.5204,
        "lng": 74.3587,
        "is_default": True,
    }, headers=auth_header(token_cust4))
    assert res_addr1.status_code == 201, f"Address 1 creation failed: {res_addr1.text}"
    addr1_id = res_addr1.json()["id"]

    # Valid Address 2 (Work)
    res_addr2 = requests.post(f"{BASE_URL}/api/addresses/", json={
        "label": "Work",
        "name": "Customer 4 Work",
        "phone": "03001234567",
        "street": "45 Tech Hub",
        "area": "DHA Phase 5",
        "city": "Lahore",
        "notes": "3rd Floor",
        "lat": 31.4700,
        "lng": 74.4100,
        "is_default": False,
    }, headers=auth_header(token_cust4))
    assert res_addr2.status_code == 201, f"Address 2 creation failed: {res_addr2.text}"
    addr2_id = res_addr2.json()["id"]

    # Verify set-default
    res_setdefault = requests.post(f"{BASE_URL}/api/addresses/{addr2_id}/set-default/", headers=auth_header(token_cust4))
    assert res_setdefault.status_code == 200, f"set-default failed: {res_setdefault.text}"
    
    # Verify in DB: only addr2 is default
    a1 = Address.objects.get(pk=addr1_id)
    a2 = Address.objects.get(pk=addr2_id)
    assert a1.is_default is False and a2.is_default is True, "DB state incorrect for is_default switching!"
    print("PASS: set-default correctly toggled default address in DB.")

    # Isolation test: User B cannot GET/PATCH/DELETE User A's address (404 expected)
    User.objects.filter(username="user_b_stage4").delete()
    requests.post(f"{BASE_URL}/api/auth/signup/", json={
        "username": "user_b_stage4",
        "email": "userb@test.com",
        "password": "securepassword123",
    })
    token_user_b = get_token("user_b_stage4", "securepassword123")

    res_leak_get = requests.get(f"{BASE_URL}/api/addresses/{addr1_id}/", headers=auth_header(token_user_b))
    assert res_leak_get.status_code == 404, f"Expected 404 on cross-user address GET, got {res_leak_get.status_code}"

    res_leak_patch = requests.patch(f"{BASE_URL}/api/addresses/{addr1_id}/", json={"city": "Karachi"}, headers=auth_header(token_user_b))
    assert res_leak_patch.status_code == 404, f"Expected 404 on cross-user address PATCH, got {res_leak_patch.status_code}"

    res_leak_del = requests.delete(f"{BASE_URL}/api/addresses/{addr1_id}/", headers=auth_header(token_user_b))
    assert res_leak_del.status_code == 404, f"Expected 404 on cross-user address DELETE, got {res_leak_del.status_code}"
    print("PASS: Address cross-user access returns 404 (no information leakage).")

    # ----------------------------------------------------
    # 3. Menu System & Public Browsing
    # ----------------------------------------------------
    print("\n--- TEST 5: Menu Browsing (Unauthenticated) ---")
    menu_res = requests.get(f"{BASE_URL}/api/menu/categories/")
    assert menu_res.status_code == 200, f"Menu categories failed: {menu_res.text}"
    categories = menu_res.json()
    assert len(categories) >= 5, f"Expected at least 5 categories, got {len(categories)}"
    
    first_cat = categories[0]
    assert "dishes" in first_cat and len(first_cat["dishes"]) > 0
    first_dish = first_cat["dishes"][0]
    assert "sizes" in first_dish and len(first_dish["sizes"]) > 0
    print(f"PASS: Public menu categories returned {len(categories)} categories with nested dishes and sizes.")

    single_dish_res = requests.get(f"{BASE_URL}/api/menu/dishes/{first_dish['slug']}/")
    assert single_dish_res.status_code == 200
    assert single_dish_res.json()["name"] == first_dish["name"]
    print(f"PASS: Single dish endpoint returned '{first_dish['name']}'.")

    # ----------------------------------------------------
    # 4. Order Creation & Price Integrity
    # ----------------------------------------------------
    print("\n--- TEST 6: Order Price Integrity (Tampered Client Total Ignored) ---")
    pizza_dish = Dish.objects.get(slug="spicy-white-pizza")
    large_size = DishSize.objects.get(dish=pizza_dish, size="Large") # 1450 PKR

    # Client tries to order qty=2 Large pizzas (real cost = 2 * 1450 = 2900) but sends total = 100 PKR!
    tampered_order_res = requests.post(f"{BASE_URL}/api/orders/", json={
        "address_id": addr2_id,
        "dish_id": pizza_dish.id,
        "dish_size_id": large_size.id,
        "qty": 2,
        "total": "100.00", # TAMPERED PRICE!
        "payment": "cod",
    }, headers=auth_header(token_cust4))
    assert tampered_order_res.status_code == 201, f"Order create failed: {tampered_order_res.text}"
    order_data = tampered_order_res.json()
    assert Decimal(str(order_data["total"])) == Decimal("2900.00"), f"Security Failure! Server accepted client total: {order_data['total']}"
    print(f"PASS: Price integrity verified! Tampered client total (100) ignored; computed server total: {order_data['total']}.")

    print("\n--- TEST 7: Multi-Item Order with Line Items & Backing OrderItem Rows ---")
    burger_dish = Dish.objects.get(slug="moon-crunch-zinger")
    burger_size = DishSize.objects.get(dish=burger_dish, size="Regular") # 520 PKR

    drink_dish = Dish.objects.get(slug="fresh-mint-lemonade")
    drink_size = DishSize.objects.get(dish=drink_dish, size="Regular") # 220 PKR

    multi_order_payload = {
        "address_id": addr2_id,
        "payment": "jazzcash",
        "items": [
            {"dish_id": pizza_dish.id, "dish_size_id": large_size.id, "qty": 1},   # 1450
            {"dish_id": burger_dish.id, "dish_size_id": burger_size.id, "qty": 2},  # 520 * 2 = 1040
            {"dish_id": drink_dish.id, "dish_size_id": drink_size.id, "qty": 3},    # 220 * 3 = 660
        ]
        # Total should be 1450 + 1040 + 660 = 3150 PKR
    }
    multi_res = requests.post(f"{BASE_URL}/api/orders/", json=multi_order_payload, headers=auth_header(token_cust4))
    assert multi_res.status_code == 201, f"Multi-item order failed: {multi_res.text}"
    multi_data = multi_res.json()
    assert Decimal(str(multi_data["total"])) == Decimal("3150.00"), f"Multi-item total mismatch: {multi_data['total']}"
    
    # Check OrderItem rows in DB
    created_order = Order.objects.get(pk=multi_data["id"])
    items_count = created_order.items.count()
    assert items_count == 3, f"Expected 3 OrderItem rows, found {items_count}"
    assert sum(item.line_total for item in created_order.items.all()) == Decimal("3150.00")
    print(f"PASS: Multi-item order created 3 OrderItem rows with exact sum 3150.00 PKR.")

    print("\n==================================================")
    print("ALL STAGE 4 TESTS PASSED WITH 100% SUCCESS!")
    print("==================================================")

if __name__ == "__main__":
    run_tests()
