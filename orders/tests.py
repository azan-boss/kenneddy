from decimal import Decimal
from django.contrib.auth.models import User
from django.core.management import call_command
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import Profile, Role, Address
from menu.models import Dish, DishSize
from orders.models import Order, OrderEvent


class OrderWorkflowTests(APITestCase):

    def setUp(self):
        call_command("seed_menu")

        # Admin user
        self.admin = User.objects.create_user(
            username="adminuser",
            email="admin@test.com",
            password="password123",
            is_staff=True,
        )
        self.admin.profile.role = Role.ADMIN
        self.admin.profile.save()

        # Kitchen user
        self.kitchen = User.objects.create_user(
            username="kitchenuser",
            email="kitchen@test.com",
            password="password123",
        )
        self.kitchen.profile.role = Role.KITCHEN
        self.kitchen.profile.save()

        # Rider user
        self.rider = User.objects.create_user(
            username="rideruser",
            email="rider@test.com",
            password="password123",
        )
        self.rider.profile.role = Role.RIDER
        self.rider.profile.full_name = "Adeel Rider"
        self.rider.profile.save()

        # Customer user
        self.customer = User.objects.create_user(
            username="custuser",
            email="cust@test.com",
            password="password123",
        )
        self.customer.profile.role = Role.CUSTOMER
        self.customer.profile.full_name = "Bilal Customer"
        self.customer.profile.save()

        self.address_payload = {
            "label": "Home",
            "name": "Bilal Customer",
            "phone": "03001234567",
            "street": "Street 4, House 11",
            "area": "Model Town",
            "city": "Narowal",
            "lat": 32.0959,
            "lng": 74.8843,
        }

    def test_kitchen_can_assign_rider_and_customer_is_forbidden(self):
        self.client.force_authenticate(user=self.customer)
        pizza = Dish.objects.get(slug="spicy-white-pizza")
        pizza_large = DishSize.objects.get(dish=pizza, size="Large")
        payload = {
            "items": [{"dish_id": pizza.id, "dish_size_id": pizza_large.id, "size": "Large", "qty": 1}],
            "payment": "cod",
            "address": self.address_payload,
        }
        res = self.client.post("/api/orders/", payload, format="json")
        order_id = res.data["id"]

        # Customer attempts to assign rider -> 403 Forbidden
        res_cust = self.client.post(f"/api/orders/{order_id}/assign-rider/", {"rider_user_id": self.rider.id}, format="json")
        self.assertEqual(res_cust.status_code, status.HTTP_403_FORBIDDEN)

        # Kitchen staff assigns rider -> 200 OK
        self.client.force_authenticate(user=self.kitchen)
        res_kitch = self.client.post(f"/api/orders/{order_id}/assign-rider/", {"rider_user_id": self.rider.id}, format="json")
        self.assertEqual(res_kitch.status_code, status.HTTP_200_OK)

        order = Order.objects.get(pk=order_id)
        self.assertEqual(order.rider_user_id, self.rider.id)
        self.assertTrue(order.timeline.filter(label="Assigned to rider").exists())

    def test_order_creation_price_integrity_and_timeline(self):
        self.client.force_authenticate(user=self.customer)
        
        # 1 Large Pizza (1800) + 1 Regular Grills (1150) = Subtotal 2950 (Delivery Free >= 2000, COD fee 150 -> Total 3100)
        pizza = Dish.objects.get(slug="spicy-white-pizza")
        pizza_large = DishSize.objects.get(dish=pizza, size="Large")
        
        grill = Dish.objects.get(slug="seekh-malai-boti")
        grill_reg = DishSize.objects.get(dish=grill, size="Regular")

        payload = {
            "items": [
                {"dish_id": pizza.id, "dish_size_id": pizza_large.id, "size": "Large", "qty": 1},
                {"dish_id": grill.id, "dish_size_id": grill_reg.id, "size": "Regular", "qty": 1},
            ],
            "payment": "cod",
            "address": self.address_payload,
        }

        res = self.client.post("/api/orders/", payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        order_id = res.data["id"]

        order = Order.objects.get(pk=order_id)
        self.assertEqual(order.subtotal, Decimal("2950.00"))
        self.assertEqual(order.delivery_fee, Decimal("0.00"))
        self.assertEqual(order.cod_fee, Decimal("150.00"))
        self.assertEqual(order.total, Decimal("3100.00"))
        self.assertEqual(order.status, "confirmed")
        self.assertEqual(order.items.count(), 2)

        # Verify OrderEvent was logged
        events = order.timeline.all()
        self.assertTrue(events.filter(label="Order placed").exists())

    def test_price_tampering_regression(self):
        """Client sends fake financial fields; server ignores them and calculates true values."""
        self.client.force_authenticate(user=self.customer)

        pizza = Dish.objects.get(slug="spicy-white-pizza")
        pizza_reg = DishSize.objects.get(dish=pizza, size="Regular") # 1450

        tampered_payload = {
            "items": [
                {"dish_slug": "spicy-white-pizza", "size": "Regular", "qty": 1},
            ],
            "payment": "cod",
            "subtotal": "1.00",
            "delivery_fee": "0.00",
            "cod_fee": "0.00",
            "discount": "10000.00",
            "total": "0.01",
            "address": self.address_payload,
        }

        res = self.client.post("/api/orders/", tampered_payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)

        order = Order.objects.get(pk=res.data["id"])
        # Subtotal = 1450.00, delivery_fee = 120.00 (since < 2000), cod_fee = 150.00, total = 1720.00
        self.assertEqual(order.subtotal, Decimal("1450.00"))
        self.assertEqual(order.delivery_fee, Decimal("120.00"))
        self.assertEqual(order.cod_fee, Decimal("150.00"))
        self.assertEqual(order.discount, Decimal("0.00"))
        self.assertEqual(order.total, Decimal("1720.00"))

    def test_order_status_progression_and_cod_settlement(self):
        self.client.force_authenticate(user=self.customer)
        pizza = Dish.objects.get(slug="spicy-white-pizza")
        order = Order.objects.create(
            user=self.customer,
            dish=pizza,
            dish_name="Spicy White Pizza",
            subtotal=Decimal("1450.00"),
            delivery_fee=Decimal("120.00"),
            cod_fee=Decimal("150.00"),
            total=Decimal("1720.00"),
            payment="cod",
            payment_status="pending",
            address=self.address_payload,
            status="confirmed",
        )

        # 1. Kitchen advances confirmed -> kitchen
        self.client.force_authenticate(user=self.kitchen)
        res = self.client.patch(f"/api/orders/{order.id}/status/", {"status": "kitchen", "note": "Baking"}, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        order.refresh_from_db()
        self.assertEqual(order.status, "kitchen")

        # 2. Kitchen advances kitchen -> packed
        res = self.client.patch(f"/api/orders/{order.id}/status/", {"status": "packed"}, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        # 3. Admin assigns rider
        self.client.force_authenticate(user=self.admin)
        res = self.client.post(f"/api/orders/{order.id}/assign-rider/", {"rider_user_id": self.rider.id}, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        # 4. Rider advances packed -> onway
        self.client.force_authenticate(user=self.rider)
        res = self.client.patch(f"/api/orders/{order.id}/status/", {"status": "onway"}, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        # 5. Rider advances onway -> delivered (auto-settles COD payment)
        res = self.client.patch(f"/api/orders/{order.id}/status/", {"status": "delivered"}, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        
        order.refresh_from_db()
        self.assertEqual(order.status, "delivered")
        self.assertEqual(order.payment_status, "verified")
        self.assertEqual(order.amount_paid, Decimal("1720.00"))
        self.assertIsNotNone(order.delivered_at)

    def test_customer_rates_delivered_order(self):
        pizza = Dish.objects.get(slug="spicy-white-pizza")
        order = Order.objects.create(
            user=self.customer,
            dish=pizza,
            dish_name="Spicy White Pizza",
            subtotal=Decimal("1450.00"),
            delivery_fee=Decimal("0.00"),
            cod_fee=Decimal("0.00"),
            total=Decimal("1450.00"),
            payment="jazzcash",
            address=self.address_payload,
            status="confirmed",
        )

        # Rate while confirmed -> rejected
        self.client.force_authenticate(user=self.customer)
        res = self.client.post(f"/api/orders/{order.id}/rate/", {"rating": 5}, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

        # Mark delivered
        order.status = "delivered"
        order.save()

        # Rate 5 stars
        res = self.client.post(f"/api/orders/{order.id}/rate/", {"rating": 5}, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["rating"], 5)

        order.refresh_from_db()
        self.assertEqual(order.rating, 5)

        # Rate again -> rejected (already rated)
        res2 = self.client.post(f"/api/orders/{order.id}/rate/", {"rating": 4}, format="json")
        self.assertEqual(res2.status_code, status.HTTP_400_BAD_REQUEST)

    def test_admin_order_controls_and_discount(self):
        pizza = Dish.objects.get(slug="spicy-white-pizza")
        order = Order.objects.create(
            user=self.customer,
            dish=pizza,
            dish_name="Spicy White Pizza",
            subtotal=Decimal("1450.00"),
            delivery_fee=Decimal("120.00"),
            cod_fee=Decimal("150.00"),
            total=Decimal("1720.00"),
            payment="cod",
            address=self.address_payload,
            status="confirmed",
        )

        self.client.force_authenticate(user=self.admin)
        patch_payload = {
            "priority": "vip",
            "eta_minutes": 20,
            "internal_notes": "VIP customer - handle with care",
            "discount": "200.00",
        }
        res = self.client.patch(f"/api/orders/{order.id}/controls/", patch_payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        order.refresh_from_db()
        self.assertEqual(order.priority, "vip")
        self.assertEqual(order.eta_minutes, 20)
        self.assertEqual(order.discount, Decimal("200.00"))
        # Recomputed total = 1450 + 120 + 150 - 200 = 1520.00
        self.assertEqual(order.total, Decimal("1520.00"))

    def test_admin_analytics_and_order_list_endpoints(self):
        pizza = Dish.objects.get(slug="spicy-white-pizza")
        order = Order.objects.create(
            user=self.customer,
            dish=pizza,
            dish_name="Spicy White Pizza",
            subtotal=Decimal("1450.00"),
            delivery_fee=Decimal("120.00"),
            cod_fee=Decimal("150.00"),
            total=Decimal("1720.00"),
            payment="cod",
            payment_status="pending",
            address=self.address_payload,
            status="confirmed",
        )

        # Non-admin rejected
        self.client.force_authenticate(user=self.customer)
        res = self.client.get("/api/orders/all/")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

        # Admin authorized
        self.client.force_authenticate(user=self.admin)
        res_list = self.client.get("/api/orders/all/")
        self.assertEqual(res_list.status_code, status.HTTP_200_OK)
        self.assertTrue(len(res_list.data) >= 1)

        # Analytics endpoint
        res_analytics = self.client.get("/api/orders/analytics/")
        self.assertEqual(res_analytics.status_code, status.HTTP_200_OK)
        self.assertIn("total_revenue", res_analytics.data)
        self.assertIn("daily_revenue_chart", res_analytics.data)
        self.assertIn("payment_method_breakdown", res_analytics.data)

    def test_admin_payments_and_verification(self):
        pizza = Dish.objects.get(slug="spicy-white-pizza")
        order = Order.objects.create(
            user=self.customer,
            dish=pizza,
            dish_name="Spicy White Pizza",
            subtotal=Decimal("1450.00"),
            delivery_fee=Decimal("0.00"),
            cod_fee=Decimal("0.00"),
            total=Decimal("1450.00"),
            payment="jazzcash",
            payment_status="pending",
            address=self.address_payload,
            status="confirmed",
        )

        self.client.force_authenticate(user=self.admin)
        # Fetch payments ledger
        res_ledger = self.client.get("/api/orders/payments/?payment_status=pending")
        self.assertEqual(res_ledger.status_code, status.HTTP_200_OK)
        self.assertTrue(len(res_ledger.data) >= 1)

        # Verify payment
        res_verify = self.client.post(
            f"/api/orders/{order.id}/verify-payment/",
            {"reference": "TID998877", "amount": "1450.00"},
            format="json",
        )
        self.assertEqual(res_verify.status_code, status.HTTP_200_OK)

        order.refresh_from_db()
        self.assertEqual(order.payment_status, "verified")
        self.assertEqual(order.payment_reference, "TID998877")
        self.assertEqual(order.amount_paid, Decimal("1450.00"))
        self.assertEqual(order.verified_by, self.admin)

    def test_admin_customer_aggregation(self):
        self.client.force_authenticate(user=self.admin)
        res = self.client.get("/api/orders/customers/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(isinstance(res.data, list))

