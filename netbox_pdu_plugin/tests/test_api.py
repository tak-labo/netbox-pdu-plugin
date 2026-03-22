"""
Test cases for NetBox PDU Plugin REST API.

Run inside Docker:
  docker compose exec netbox python manage.py test netbox_pdu_plugin.tests.test_api --parallel -v2
"""

from ..models import ManagedPDU, PDUInlet, PDUOutlet
from ..testing import PluginAPITestCase
from ..testing.utils import disable_warnings
from .test_models import create_test_device, create_test_pdu


class ManagedPDUAPITest(PluginAPITestCase):
    """Tests for the ManagedPDU REST API endpoints."""

    @classmethod
    def setUpTestData(cls):
        cls.device1 = create_test_device('PDU-API-1')
        cls.device2 = create_test_device('PDU-API-2')
        cls.device3 = create_test_device('PDU-API-3')
        cls.pdu1 = create_test_pdu(cls.device1)
        cls.pdu2 = create_test_pdu(cls.device2)

    def setUp(self):
        super().setUp()
        self.list_url_name = 'plugins-api:netbox_pdu_plugin-api:managedpdu-list'
        self.detail_url_name = 'plugins-api:netbox_pdu_plugin-api:managedpdu-detail'

    def test_list_managed_pdus(self):
        self.add_permissions('netbox_pdu_plugin.view_managedpdu')
        response = self.client.get(self._get_list_url())
        self.assertHttpStatus(response, 200)
        self.assertGreaterEqual(response.data['count'], 2)

    def test_list_without_permission(self):
        with disable_warnings('django.request'):
            response = self.client.get(self._get_list_url())
            self.assertHttpStatus(response, 403)

    def test_get_managed_pdu(self):
        self.add_permissions('netbox_pdu_plugin.view_managedpdu')
        url = self._get_detail_url(self.pdu1)
        response = self.client.get(url)
        self.assertHttpStatus(response, 200)
        self.assertEqual(response.data['id'], self.pdu1.pk)

    def test_create_without_permission(self):
        # api_password is intentionally excluded from the serializer for security.
        # Creating via API is not supported; use the web UI instead.
        data = {'device': self.device3.pk, 'api_url': 'https://x.example.com'}
        with disable_warnings('django.request'):
            response = self.client.post(self._get_list_url(), data, format='json')
            self.assertHttpStatus(response, 403)

    def test_delete_managed_pdu(self):
        self.add_permissions('netbox_pdu_plugin.delete_managedpdu')
        pdu = create_test_pdu(create_test_device('PDU-DEL'))
        url = self._get_detail_url(pdu)
        response = self.client.delete(url)
        self.assertHttpStatus(response, 204)
        self.assertFalse(ManagedPDU.objects.filter(pk=pdu.pk).exists())


class PDUOutletAPITest(PluginAPITestCase):
    """Tests for the PDUOutlet REST API endpoints."""

    @classmethod
    def setUpTestData(cls):
        cls.pdu = create_test_pdu()
        cls.outlet1 = PDUOutlet.objects.create(managed_pdu=cls.pdu, outlet_number=1)
        cls.outlet2 = PDUOutlet.objects.create(managed_pdu=cls.pdu, outlet_number=2)

    def setUp(self):
        super().setUp()
        self.list_url_name = 'plugins-api:netbox_pdu_plugin-api:pduoutlet-list'
        self.detail_url_name = 'plugins-api:netbox_pdu_plugin-api:pduoutlet-detail'

    def test_list_outlets(self):
        self.add_permissions('netbox_pdu_plugin.view_pduoutlet')
        response = self.client.get(self._get_list_url())
        self.assertHttpStatus(response, 200)
        self.assertGreaterEqual(response.data['count'], 2)

    def test_get_outlet(self):
        self.add_permissions('netbox_pdu_plugin.view_pduoutlet')
        url = self._get_detail_url(self.outlet1)
        response = self.client.get(url)
        self.assertHttpStatus(response, 200)
        self.assertEqual(response.data['outlet_number'], 1)


class PDUInletAPITest(PluginAPITestCase):
    """Tests for the PDUInlet REST API endpoints."""

    @classmethod
    def setUpTestData(cls):
        cls.pdu = create_test_pdu()
        cls.inlet1 = PDUInlet.objects.create(managed_pdu=cls.pdu, inlet_number=1)

    def setUp(self):
        super().setUp()
        self.list_url_name = 'plugins-api:netbox_pdu_plugin-api:pduinlet-list'
        self.detail_url_name = 'plugins-api:netbox_pdu_plugin-api:pduinlet-detail'

    def test_list_inlets(self):
        self.add_permissions('netbox_pdu_plugin.view_pduinlet')
        response = self.client.get(self._get_list_url())
        self.assertHttpStatus(response, 200)
        self.assertGreaterEqual(response.data['count'], 1)

    def test_get_inlet(self):
        self.add_permissions('netbox_pdu_plugin.view_pduinlet')
        url = self._get_detail_url(self.inlet1)
        response = self.client.get(url)
        self.assertHttpStatus(response, 200)
        self.assertEqual(response.data['inlet_number'], 1)
