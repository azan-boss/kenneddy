from django.contrib.auth.models import User
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from accounts.models import Profile, Role, Address


class AuthAndAccountTests(APITestCase):

    def setUp(self):
        # Admin user
        self.admin_user = User.objects.create_user(
            username="adminuser",
            email="admin@test.com",
            password="password123",
            is_staff=True,
        )
        self.admin_profile = Profile.objects.get(user=self.admin_user)
        self.admin_profile.role = Role.ADMIN
        self.admin_profile.full_name = "Admin Master"
        self.admin_profile.save()

        # Customer user
        self.customer_user = User.objects.create_user(
            username="custuser",
            email="customer@test.com",
            password="password123",
        )
        self.customer_profile = Profile.objects.get(user=self.customer_user)
        self.customer_profile.role = Role.CUSTOMER
        self.customer_profile.full_name = "Bilal Customer"
        self.customer_profile.phone = "03001234567"
        self.customer_profile.save()
        self.customer_user.refresh_from_db()

    def test_customer_signup(self):
        url = "/api/auth/signup/"
        payload = {
            "username": "newcustomer",
            "email": "newcust@test.com",
            "password": "strongpassword123",
            "requested_role": "customer",
        }
        res = self.client.post(url, payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data["status"], "active")

        user = User.objects.get(username="newcustomer")
        self.assertTrue(user.is_active)
        self.assertEqual(user.profile.role, Role.CUSTOMER)

    def test_rider_signup_is_pending_approval(self):
        url = "/api/auth/signup/"
        payload = {
            "username": "newrider",
            "email": "newrider@test.com",
            "password": "strongpassword123",
            "requested_role": "rider",
        }
        res = self.client.post(url, payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data["status"], "pending_approval")

        user = User.objects.get(username="newrider")
        self.assertFalse(user.is_active)
        self.assertEqual(user.profile.role, Role.RIDER)

    def test_jwt_login_returns_user_metadata(self):
        url = "/api/auth/login/"
        payload = {
            "username": "custuser",
            "password": "password123",
        }
        res = self.client.post(url, payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn("access", res.data)
        self.assertIn("refresh", res.data)
        self.assertIn("user", res.data)

        user_data = res.data["user"]
        self.assertEqual(user_data["username"], "custuser")
        self.assertEqual(user_data["email"], "customer@test.com")
        self.assertEqual(user_data["role"], "customer")
        self.assertEqual(user_data["full_name"], "Bilal Customer")

    def test_jwt_token_refresh(self):
        # First login to get tokens
        login_res = self.client.post("/api/auth/login/", {"username": "custuser", "password": "password123"}, format="json")
        refresh_token = login_res.data["refresh"]

        # Call refresh
        refresh_res = self.client.post("/api/auth/refresh/", {"refresh": refresh_token}, format="json")
        self.assertEqual(refresh_res.status_code, status.HTTP_200_OK)
        self.assertIn("access", refresh_res.data)

    def test_profile_read_and_update(self):
        self.client.force_authenticate(user=self.customer_user)
        res = self.client.get("/api/profile/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["username"], "custuser")
        self.assertEqual(res.data["full_name"], "Bilal Customer")

        # Update full name and phone
        patch_res = self.client.patch("/api/profile/", {"full_name": "Bilal Ahmed", "phone": "03009998877"}, format="json")
        self.assertEqual(patch_res.status_code, status.HTTP_200_OK)
        self.assertEqual(patch_res.data["full_name"], "Bilal Ahmed")
        self.assertEqual(patch_res.data["phone"], "03009998877")

    def test_address_crud(self):
        self.client.force_authenticate(user=self.customer_user)

        # Create address
        payload = {
            "label": "Home",
            "name": "Bilal Ahmed",
            "phone": "03001234567",
            "street": "House 12, Street 3",
            "area": "Kacheri Road",
            "city": "Narowal",
            "lat": 32.0959,
            "lng": 74.8843,
            "is_default": True,
        }
        create_res = self.client.post("/api/addresses/", payload, format="json")
        self.assertEqual(create_res.status_code, status.HTTP_201_CREATED)
        addr_id = create_res.data["id"]

        # Read addresses
        list_res = self.client.get("/api/addresses/")
        self.assertEqual(list_res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(list_res.data), 1)

        # Delete address
        del_res = self.client.delete(f"/api/addresses/{addr_id}/")
        self.assertEqual(del_res.status_code, status.HTTP_204_NO_CONTENT)

    def test_admin_approves_rider(self):
        # Create inactive rider
        rider_user = User.objects.create_user(
            username="riderpending",
            email="riderpending@test.com",
            password="password123",
            is_active=False,
        )
        rider_user.profile.role = Role.RIDER
        rider_user.profile.save()

        # Admin approves
        self.client.force_authenticate(user=self.admin_user)
        approve_url = f"/api/admin/riders/{rider_user.id}/approve/"
        res = self.client.post(approve_url, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        rider_user.refresh_from_db()
        self.assertTrue(rider_user.is_active)
