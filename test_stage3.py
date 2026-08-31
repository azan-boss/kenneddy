import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

import asyncio
import json
import requests
import websockets
from django.contrib.auth.models import User
from accounts.models import Profile, Role

BASE_URL = "http://127.0.0.1:8000"
WS_URL = "ws://127.0.0.1:8000"

def setup_users():
    users_data = [
        ("admin_user", "admin@test.com", "pass12345", Role.ADMIN),
        ("kitchen_user", "kitchen@test.com", "pass12345", Role.KITCHEN),
        ("rider_one", "rider1@test.com", "pass12345", Role.RIDER),
        ("rider_two", "rider2@test.com", "pass12345", Role.RIDER),
        ("cust_one", "cust1@test.com", "pass12345", Role.CUSTOMER),
        ("cust_two", "cust2@test.com", "pass12345", Role.CUSTOMER),
    ]

    user_ids = {}
    for uname, email, pwd, role in users_data:
        u, created = User.objects.get_or_create(username=uname, defaults={"email": email})
        u.set_password(pwd)
        u.save()
        prof, _ = Profile.objects.get_or_create(user=u)
        prof.role = role
        if role == Role.RIDER:
            prof.full_name = f"Rider {uname}"
            prof.phone = "03001112233"
        prof.save()
        user_ids[uname] = u.id
    print("Users setup completed.")
    return user_ids

def get_token(username, password="pass12345"):
    res = requests.post(f"{BASE_URL}/api/auth/login/", json={"username": username, "password": password})
    assert res.status_code == 200, f"Login failed for {username}: {res.text}"
    return res.json()["access"]

async def run_tests(user_ids):
    tokens = {
        "admin": get_token("admin_user"),
        "kitchen": get_token("kitchen_user"),
        "rider1": get_token("rider_one"),
        "rider2": get_token("rider_two"),
        "cust1": get_token("cust_one"),
        "cust2": get_token("cust_two"),
    }
    
    auth_headers = {k: {"Authorization": f"Bearer {v}", "Content-Type": "application/json"} for k, v in tokens.items()}

    print("\n--- 1. Place order as customer 1 ---")
    order_payload = {
        "dish_name": "Special Moon Platter",
        "size": "Family",
        "qty": 1,
        "total": "2500.00",
        "payment": "cod",
        "address": {
            "label": "Home",
            "name": "Customer One",
            "phone": "03009998877",
            "city": "Lahore",
            "street": "Mall Road",
            "lat": 31.5204,
            "lng": 74.3587
        }
    }
    res = requests.post(f"{BASE_URL}/api/orders/", json=order_payload, headers=auth_headers["cust1"])
    assert res.status_code == 201, f"Order create failed: {res.text}"
    order = res.json()
    order_id = order["id"]
    print(f"Created order {order_id} (code: {order['order_code']}), initial status: {order['status']}")

    print("\n--- 2. Customer attempts PATCH status -> expect 403 ---")
    res = requests.patch(f"{BASE_URL}/api/orders/{order_id}/status/", json={"status": "kitchen"}, headers=auth_headers["cust1"])
    print(f"Customer status update response code: {res.status_code}")
    assert res.status_code == 403, f"Expected 403 for customer, got {res.status_code}"

    print("\n--- 3. Kitchen moves confirmed -> kitchen -> expect 200 ---")
    res = requests.patch(f"{BASE_URL}/api/orders/{order_id}/status/", json={"status": "kitchen"}, headers=auth_headers["kitchen"])
    print(f"Kitchen update to 'kitchen' response code: {res.status_code}, status: {res.json().get('status')}")
    assert res.status_code == 200 and res.json()["status"] == "kitchen"

    print("\n--- 4. Kitchen moves kitchen -> packed -> expect 200 ---")
    res = requests.patch(f"{BASE_URL}/api/orders/{order_id}/status/", json={"status": "packed"}, headers=auth_headers["kitchen"])
    print(f"Kitchen update to 'packed' response code: {res.status_code}, status: {res.json().get('status')}")
    assert res.status_code == 200 and res.json()["status"] == "packed"

    print("\n--- 5. Kitchen tries packed -> onway -> expect 403 ---")
    res = requests.patch(f"{BASE_URL}/api/orders/{order_id}/status/", json={"status": "onway"}, headers=auth_headers["kitchen"])
    print(f"Kitchen update to 'onway' response code: {res.status_code}")
    assert res.status_code == 403, f"Expected 403 for kitchen onway, got {res.status_code}"

    print("\n--- 6. Assign rider test: non-admin tries assign -> expect 403 ---")
    res = requests.post(f"{BASE_URL}/api/orders/{order_id}/assign-rider/", json={"rider_user_id": 1}, headers=auth_headers["kitchen"])
    assert res.status_code == 403, f"Expected 403 for non-admin assign-rider, got {res.status_code}"

    print("\n--- 7. Assign rider test: assigning a customer as rider -> expect 400 ---")
    cust2_user_id = user_ids["cust_two"]
    rider1_user_id = user_ids["rider_one"]
    rider2_user_id = user_ids["rider_two"]

    res = requests.post(f"{BASE_URL}/api/orders/{order_id}/assign-rider/", json={"rider_user_id": cust2_user_id}, headers=auth_headers["admin"])
    print(f"Assign customer as rider response code: {res.status_code}, detail: {res.json().get('detail')}")
    assert res.status_code == 400, f"Expected 400 for assigning customer as rider, got {res.status_code}"

    print("\n--- 8. Admin assigns rider1 -> expect 200 ---")
    res = requests.post(f"{BASE_URL}/api/orders/{order_id}/assign-rider/", json={"rider_user_id": rider1_user_id, "bike": "Honda CD70"}, headers=auth_headers["admin"])
    print(f"Assign rider response code: {res.status_code}, rider: {res.json().get('rider')}")
    assert res.status_code == 200 and res.json()["rider_user_id"] == rider1_user_id

    print("\n--- 9. Rider2 (unassigned) tries packed -> onway -> expect 403 ---")
    res = requests.patch(f"{BASE_URL}/api/orders/{order_id}/status/", json={"status": "onway"}, headers=auth_headers["rider2"])
    print(f"Unassigned rider status update response code: {res.status_code}")
    assert res.status_code == 403, f"Expected 403 for unassigned rider, got {res.status_code}"

    print("\n--- 10. Rider1 tries POST rider-location while status is still 'packed' -> expect 400 ---")
    res = requests.post(f"{BASE_URL}/api/orders/{order_id}/rider-location/", json={"lat": 31.521, "lng": 74.359}, headers=auth_headers["rider1"])
    print(f"Location push when packed response code: {res.status_code}, detail: {res.json().get('detail')}")
    assert res.status_code == 400, f"Expected 400 for location push before onway, got {res.status_code}"

    print("\n--- 11. Assigned rider (Rider1) moves packed -> onway -> expect 200 ---")
    res = requests.patch(f"{BASE_URL}/api/orders/{order_id}/status/", json={"status": "onway"}, headers=auth_headers["rider1"])
    print(f"Rider1 update to 'onway' response code: {res.status_code}, status: {res.json().get('status')}")
    assert res.status_code == 200 and res.json()["status"] == "onway"

    print("\n--- 12. Unassigned user (Rider2 / cust2) tries POST rider-location -> expect 403 ---")
    res = requests.post(f"{BASE_URL}/api/orders/{order_id}/rider-location/", json={"lat": 31.521, "lng": 74.359}, headers=auth_headers["rider2"])
    print(f"Unassigned rider location push code: {res.status_code}")
    assert res.status_code == 403, f"Expected 403 for unassigned rider location push, got {res.status_code}"

    print("\n--- 13. WebSocket connection tests ---")
    # 13a: Unrelated user (cust2) connects -> expect rejected/closed
    ws_url_cust2 = f"{WS_URL}/ws/orders/{order_id}/?token={tokens['cust2']}"
    try:
        async with websockets.connect(ws_url_cust2) as ws:
            msg = await asyncio.wait_for(ws.recv(), timeout=2.0)
            print("Cust2 unexpectedly connected!")
            assert False, "Cust2 should have been rejected"
    except (websockets.exceptions.WebSocketException, websockets.exceptions.ConnectionClosed, asyncio.TimeoutError) as e:
        print(f"Cust2 correctly rejected / closed: {e}")

    # 13b: Order owner (cust1) connects -> succeeds and receives live updates!
    ws_url_cust1 = f"{WS_URL}/ws/orders/{order_id}/?token={tokens['cust1']}"
    async with websockets.connect(ws_url_cust1) as ws:
        print("Cust1 connected to WebSocket successfully.")
        
        # 14. Assigned rider (Rider1) pushes location while status=onway
        print("\n--- 14. Rider1 pushes location -> expect 200 & WS push received ---")
        loc_res = requests.post(
            f"{BASE_URL}/api/orders/{order_id}/rider-location/",
            json={"lat": 31.5225, "lng": 74.3601, "eta_minutes": 15},
            headers=auth_headers["rider1"]
        )
        assert loc_res.status_code == 200, f"Rider location push failed: {loc_res.text}"
        print(f"Location push response: {loc_res.json()}")

        # Wait for message over websocket
        ws_msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
        data = json.loads(ws_msg)
        print(f"Received WS live update: {data}")
        assert data["rider_lat"] == 31.5225
        assert data["rider_lng"] == 74.3601
        assert data["eta_minutes"] == 15
        assert data["status"] == "onway"
        print("WebSocket live update assertion PASSED!")

    print("\n--- 15. Assigned rider moves onway -> delivered -> expect 200 ---")
    res = requests.patch(f"{BASE_URL}/api/orders/{order_id}/status/", json={"status": "delivered"}, headers=auth_headers["rider1"])
    print(f"Rider1 update to 'delivered' response code: {res.status_code}, status: {res.json().get('status')}")
    assert res.status_code == 200 and res.json()["status"] == "delivered"

    print("\n==========================================")
    print("ALL STAGE 3 DEFINITION OF DONE TESTS PASSED!")
    print("==========================================")

if __name__ == "__main__":
    user_ids = setup_users()
    asyncio.run(run_tests(user_ids))
