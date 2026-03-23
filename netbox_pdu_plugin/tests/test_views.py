"""
Test cases for NetBox PDU Plugin views.

Run inside Docker:
  docker compose exec netbox python manage.py test netbox_pdu_plugin.tests.test_views -v2
"""

from unittest.mock import MagicMock, patch

from django.urls import reverse

from ..backends.base import PDUClientError
from ..choices import OutletStatusChoices, VendorChoices
from ..models import ManagedPDU, PDUInlet, PDUOutlet
from ..testing import PluginViewTestCase
from ..testing.utils import disable_warnings
from .test_models import create_test_device, create_test_pdu


class ManagedPDUViewTest(PluginViewTestCase):
    """Tests for ManagedPDU CRUD views."""

    @classmethod
    def setUpTestData(cls):
        cls.device1 = create_test_device("PDU-VIEW-1")
        cls.device2 = create_test_device("PDU-VIEW-2")
        cls.device3 = create_test_device("PDU-VIEW-3")
        cls.pdu = create_test_pdu(cls.device1)

    def setUp(self):
        super().setUp()
        self.base_url = "plugins:netbox_pdu_plugin:managedpdu"

    def test_list_view(self):
        self.add_permissions("netbox_pdu_plugin.view_managedpdu")
        url = self._get_url("list")
        response = self.client.get(url)
        self.assertHttpStatus(response, 200)

    def test_list_view_without_permission(self):
        with disable_warnings("django.request"):
            url = self._get_url("list")
            response = self.client.get(url)
            self.assertHttpStatus(response, 403)

    def test_detail_view(self):
        self.add_permissions("netbox_pdu_plugin.view_managedpdu")
        url = self._get_url("detail", self.pdu)
        response = self.client.get(url)
        self.assertHttpStatus(response, 200)
        self.assertEqual(response.context["object"], self.pdu)

    def test_add_view_get(self):
        self.add_permissions("netbox_pdu_plugin.add_managedpdu")
        url = self._get_url("add")
        response = self.client.get(url)
        self.assertHttpStatus(response, 200)

    def test_add_view_post(self):
        # Use superuser to bypass ObjectPermission and form field restrictions.
        superuser = self.create_test_user(username="superuser_add", is_superuser=True)
        self.client.force_login(superuser)
        url = self._get_url("add")
        form_data = self.post_data(
            {
                "device": self.device2,
                "vendor": VendorChoices.RARITAN,
                "api_url": "https://new.example.com",
                "api_username": "admin",
                "api_password": "secret",
                "verify_ssl": False,
            }
        )
        response = self.client.post(url, form_data, follow=True)
        self.assertHttpStatus(response, 200)
        self.assertTrue(ManagedPDU.objects.filter(device=self.device2).exists())

    def test_edit_view(self):
        superuser = self.create_test_user(username="superuser_edit", is_superuser=True)
        self.client.force_login(superuser)
        url = self._get_url("edit", self.pdu)
        form_data = self.post_data(
            {
                "device": self.device1,
                "vendor": VendorChoices.RARITAN,
                "api_url": "https://edited.example.com",
                "api_username": "admin",
                "api_password": "secret",
                "verify_ssl": False,
            }
        )
        response = self.client.post(url, form_data, follow=True)
        self.assertHttpStatus(response, 200)
        self.pdu.refresh_from_db()
        self.assertEqual(self.pdu.api_url, "https://edited.example.com")

    def test_delete_view(self):
        superuser = self.create_test_user(username="superuser_del", is_superuser=True)
        self.client.force_login(superuser)
        pdu = create_test_pdu(self.device3)
        url = self._get_url("delete", pdu)
        response = self.client.post(url, {"confirm": True}, follow=True)
        self.assertHttpStatus(response, 200)
        self.assertFalse(ManagedPDU.objects.filter(pk=pdu.pk).exists())


class PDUOutletViewTest(PluginViewTestCase):
    """Tests for PDUOutlet views."""

    @classmethod
    def setUpTestData(cls):
        cls.pdu = create_test_pdu()
        cls.outlet = PDUOutlet.objects.create(
            managed_pdu=cls.pdu,
            outlet_number=1,
            outlet_name="Outlet 1",
        )

    def setUp(self):
        super().setUp()
        self.base_url = "plugins:netbox_pdu_plugin:pduoutlet"

    def test_list_view(self):
        self.add_permissions("netbox_pdu_plugin.view_pduoutlet")
        url = self._get_url("list")
        response = self.client.get(url)
        self.assertHttpStatus(response, 200)

    def test_detail_view(self):
        self.add_permissions("netbox_pdu_plugin.view_pduoutlet")
        url = self._get_url("detail", self.outlet)
        response = self.client.get(url)
        self.assertHttpStatus(response, 200)


class PDUInletViewTest(PluginViewTestCase):
    """Tests for PDUInlet views."""

    @classmethod
    def setUpTestData(cls):
        cls.pdu = create_test_pdu()
        cls.inlet = PDUInlet.objects.create(
            managed_pdu=cls.pdu,
            inlet_number=1,
            inlet_name="Inlet 1",
        )

    def setUp(self):
        super().setUp()
        self.base_url = "plugins:netbox_pdu_plugin:pduinlet"

    def test_list_view(self):
        self.add_permissions("netbox_pdu_plugin.view_pduinlet")
        url = self._get_url("list")
        response = self.client.get(url)
        self.assertHttpStatus(response, 200)

    def test_detail_view(self):
        self.add_permissions("netbox_pdu_plugin.view_pduinlet")
        url = self._get_url("detail", self.inlet)
        response = self.client.get(url)
        self.assertHttpStatus(response, 200)


class PDUOutletPowerViewTest(PluginViewTestCase):
    """Tests for PDUOutlet power control views (ON / OFF / cycle)."""

    @classmethod
    def setUpTestData(cls):
        cls.pdu = create_test_pdu()
        cls.outlet = PDUOutlet.objects.create(
            managed_pdu=cls.pdu,
            outlet_number=1,
            outlet_name="Outlet 1",
        )

    def _url(self, action):
        return reverse(f"plugins:netbox_pdu_plugin:pduoutlet_{action}", kwargs={"pk": self.outlet.pk})

    def test_power_on_without_permission(self):
        # View does its own permission check and redirects — no 403.
        response = self.client.post(self._url("power_on"))
        self.assertHttpStatus(response, 302)

    @patch("netbox_pdu_plugin.views.get_pdu_client")
    def test_power_on(self, mock_get_client):
        self.add_permissions("netbox_pdu_plugin.change_managedpdu")
        mock_client = MagicMock()
        mock_client.get_outlet_power_state_by_index.return_value = "on"
        mock_get_client.return_value = mock_client

        response = self.client.post(self._url("power_on"))

        self.assertHttpStatus(response, 302)
        mock_client.set_outlet_power_state.assert_called_once_with(0, "on")
        mock_client.get_outlet_power_state_by_index.assert_called_once_with(0)
        self.outlet.refresh_from_db()
        self.assertEqual(self.outlet.status, OutletStatusChoices.ON)

    @patch("netbox_pdu_plugin.views.get_pdu_client")
    def test_power_off(self, mock_get_client):
        self.add_permissions("netbox_pdu_plugin.change_managedpdu")
        mock_client = MagicMock()
        mock_client.get_outlet_power_state_by_index.return_value = "off"
        mock_get_client.return_value = mock_client

        response = self.client.post(self._url("power_off"))

        self.assertHttpStatus(response, 302)
        mock_client.set_outlet_power_state.assert_called_once_with(0, "off")
        self.outlet.refresh_from_db()
        self.assertEqual(self.outlet.status, OutletStatusChoices.OFF)

    @patch("netbox_pdu_plugin.views.django_rq")
    @patch("netbox_pdu_plugin.views.get_pdu_client")
    def test_power_cycle(self, mock_get_client, mock_rq):
        self.add_permissions("netbox_pdu_plugin.change_managedpdu")
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_queue = MagicMock()
        mock_rq.get_queue.return_value = mock_queue

        response = self.client.post(self._url("power_cycle"))

        self.assertHttpStatus(response, 302)
        mock_client.set_outlet_power_state.assert_called_once_with(0, "cycle")
        # Background job must be enqueued for cycle
        mock_queue.enqueue_in.assert_called_once()

    def test_power_on_without_permission_does_not_call_backend(self):
        with patch("netbox_pdu_plugin.views.get_pdu_client") as mock_get_client:
            self.client.post(self._url("power_on"))
            mock_get_client.assert_not_called()


class PDUOutletPushNameViewTest(PluginViewTestCase):
    """Tests for PDUOutletPushNameView."""

    @classmethod
    def setUpTestData(cls):
        cls.pdu = create_test_pdu()
        cls.outlet = PDUOutlet.objects.create(
            managed_pdu=cls.pdu,
            outlet_number=1,
            outlet_name="Test Server",
        )

    def _url(self):
        return reverse("plugins:netbox_pdu_plugin:pduoutlet_push_name", kwargs={"pk": self.outlet.pk})

    def test_push_name_without_permission_redirects(self):
        response = self.client.post(self._url())
        self.assertHttpStatus(response, 302)

    def test_push_name_without_permission_does_not_call_backend(self):
        with patch("netbox_pdu_plugin.views.get_pdu_client") as mock_get_client:
            self.client.post(self._url())
            mock_get_client.assert_not_called()

    @patch("netbox_pdu_plugin.views.get_pdu_client")
    def test_push_name(self, mock_get_client):
        self.add_permissions("netbox_pdu_plugin.change_managedpdu")
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        response = self.client.post(self._url())

        self.assertHttpStatus(response, 302)
        mock_client.set_outlet_name.assert_called_once_with(0, "Test Server")

    @patch("netbox_pdu_plugin.views.get_pdu_client")
    def test_push_name_pdu_error_does_not_update_netbox_label(self, mock_get_client):
        self.add_permissions("netbox_pdu_plugin.change_managedpdu")
        mock_client = MagicMock()
        mock_client.set_outlet_name.side_effect = PDUClientError("connection refused")
        mock_get_client.return_value = mock_client

        from dcim.models import PowerOutlet as NbPowerOutlet

        po = NbPowerOutlet.objects.create(
            device=self.pdu.device,
            name="Outlet 1",
            label="old label",
        )

        self.client.post(self._url())

        po.refresh_from_db()
        self.assertEqual(po.label, "old label")


class PDUInletPushNameViewTest(PluginViewTestCase):
    """Tests for PDUInletPushNameView."""

    @classmethod
    def setUpTestData(cls):
        cls.pdu = create_test_pdu()
        cls.inlet = PDUInlet.objects.create(
            managed_pdu=cls.pdu,
            inlet_number=1,
            inlet_name="Main Input",
        )

    def _url(self):
        return reverse("plugins:netbox_pdu_plugin:pduinlet_push_name", kwargs={"pk": self.inlet.pk})

    def test_push_name_without_permission_redirects(self):
        response = self.client.post(self._url())
        self.assertHttpStatus(response, 302)

    def test_push_name_without_permission_does_not_call_backend(self):
        with patch("netbox_pdu_plugin.views.get_pdu_client") as mock_get_client:
            self.client.post(self._url())
            mock_get_client.assert_not_called()

    @patch("netbox_pdu_plugin.views.get_pdu_client")
    def test_push_name(self, mock_get_client):
        self.add_permissions("netbox_pdu_plugin.change_managedpdu")
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        response = self.client.post(self._url())

        self.assertHttpStatus(response, 302)
        mock_client.set_inlet_name.assert_called_once_with(0, "Main Input")

    @patch("netbox_pdu_plugin.views.get_pdu_client")
    def test_push_name_pdu_error_does_not_update_netbox_label(self, mock_get_client):
        self.add_permissions("netbox_pdu_plugin.change_managedpdu")
        mock_client = MagicMock()
        mock_client.set_inlet_name.side_effect = PDUClientError("connection refused")
        mock_get_client.return_value = mock_client

        from dcim.models import PowerPort as NbPowerPort

        pp = NbPowerPort.objects.create(
            device=self.pdu.device,
            name="Power Port 1",
            label="old label",
        )

        self.client.post(self._url())

        pp.refresh_from_db()
        self.assertEqual(pp.label, "old label")


class PDUOutletBulkPowerViewTest(PluginViewTestCase):
    """Tests for PDUOutletBulkPowerView (bulk ON/OFF)."""

    @classmethod
    def setUpTestData(cls):
        cls.pdu = create_test_pdu()
        cls.pdu2_device = create_test_device("PDU-BULK-2")
        cls.pdu2 = create_test_pdu(cls.pdu2_device)
        cls.outlet1 = PDUOutlet.objects.create(
            managed_pdu=cls.pdu,
            outlet_number=1,
            outlet_name="Outlet 1",
        )
        cls.outlet2 = PDUOutlet.objects.create(
            managed_pdu=cls.pdu,
            outlet_number=2,
            outlet_name="Outlet 2",
        )
        cls.outlet_other_pdu = PDUOutlet.objects.create(
            managed_pdu=cls.pdu2,
            outlet_number=1,
            outlet_name="Other PDU Outlet",
        )

    def _url(self):
        return reverse(
            "plugins:netbox_pdu_plugin:pduoutlet_bulk_power",
            kwargs={"pk": self.pdu.pk},
        )

    def test_bulk_power_without_permission_redirects(self):
        response = self.client.post(self._url(), {"action": "on", "pk": [self.outlet1.pk]})
        self.assertHttpStatus(response, 302)

    def test_bulk_power_without_permission_does_not_call_backend(self):
        with patch("netbox_pdu_plugin.views.get_pdu_client") as mock_get_client:
            self.client.post(self._url(), {"action": "on", "pk": [self.outlet1.pk]})
            mock_get_client.assert_not_called()

    @patch("netbox_pdu_plugin.views.get_pdu_client")
    def test_bulk_power_on(self, mock_get_client):
        self.add_permissions("netbox_pdu_plugin.change_managedpdu")
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        response = self.client.post(
            self._url(), {"action": "on", "pk": [self.outlet1.pk, self.outlet2.pk]}
        )

        self.assertHttpStatus(response, 302)
        mock_client.set_outlet_power_state.assert_any_call(0, "on")
        mock_client.set_outlet_power_state.assert_any_call(1, "on")
        self.assertEqual(mock_client.set_outlet_power_state.call_count, 2)
        self.outlet1.refresh_from_db()
        self.outlet2.refresh_from_db()
        self.assertEqual(self.outlet1.status, OutletStatusChoices.ON)
        self.assertEqual(self.outlet2.status, OutletStatusChoices.ON)

    @patch("netbox_pdu_plugin.views.get_pdu_client")
    def test_bulk_power_off(self, mock_get_client):
        self.add_permissions("netbox_pdu_plugin.change_managedpdu")
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        response = self.client.post(
            self._url(), {"action": "off", "pk": [self.outlet1.pk, self.outlet2.pk]}
        )

        self.assertHttpStatus(response, 302)
        self.outlet1.refresh_from_db()
        self.outlet2.refresh_from_db()
        self.assertEqual(self.outlet1.status, OutletStatusChoices.OFF)
        self.assertEqual(self.outlet2.status, OutletStatusChoices.OFF)

    @patch("netbox_pdu_plugin.views.get_pdu_client")
    def test_bulk_power_no_pks_returns_warning(self, mock_get_client):
        self.add_permissions("netbox_pdu_plugin.change_managedpdu")
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        response = self.client.post(self._url(), {"action": "on"})

        self.assertHttpStatus(response, 302)
        mock_client.set_outlet_power_state.assert_not_called()

    @patch("netbox_pdu_plugin.views.get_pdu_client")
    def test_bulk_power_invalid_action_returns_error(self, mock_get_client):
        self.add_permissions("netbox_pdu_plugin.change_managedpdu")
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        response = self.client.post(
            self._url(), {"action": "cycle", "pk": [self.outlet1.pk]}
        )

        self.assertHttpStatus(response, 302)
        mock_client.set_outlet_power_state.assert_not_called()

    @patch("netbox_pdu_plugin.views.get_pdu_client")
    def test_bulk_power_ignores_outlets_from_other_pdu(self, mock_get_client):
        self.add_permissions("netbox_pdu_plugin.change_managedpdu")
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        response = self.client.post(
            self._url(),
            {"action": "on", "pk": [self.outlet1.pk, self.outlet_other_pdu.pk]},
        )

        self.assertHttpStatus(response, 302)
        mock_client.set_outlet_power_state.assert_called_once_with(0, "on")

    @patch("netbox_pdu_plugin.views.get_pdu_client")
    def test_bulk_power_continues_after_api_error(self, mock_get_client):
        self.add_permissions("netbox_pdu_plugin.change_managedpdu")
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.set_outlet_power_state.side_effect = [
            PDUClientError("timeout"),
            None,
        ]

        response = self.client.post(
            self._url(), {"action": "on", "pk": [self.outlet1.pk, self.outlet2.pk]}
        )

        self.assertHttpStatus(response, 302)
        self.assertEqual(mock_client.set_outlet_power_state.call_count, 2)
        self.outlet2.refresh_from_db()
        self.assertEqual(self.outlet2.status, OutletStatusChoices.ON)
