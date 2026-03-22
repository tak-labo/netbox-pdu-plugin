"""
Test cases for NetBox PDU Plugin views.

Run inside Docker:
  docker compose exec netbox python manage.py test netbox_pdu_plugin.tests.test_views -v2
"""


from ..choices import VendorChoices
from ..models import ManagedPDU, PDUInlet, PDUOutlet
from ..testing import PluginViewTestCase
from ..testing.utils import disable_warnings
from .test_models import create_test_device, create_test_pdu


class ManagedPDUViewTest(PluginViewTestCase):
    """Tests for ManagedPDU CRUD views."""

    @classmethod
    def setUpTestData(cls):
        cls.device1 = create_test_device('PDU-VIEW-1')
        cls.device2 = create_test_device('PDU-VIEW-2')
        cls.device3 = create_test_device('PDU-VIEW-3')
        cls.pdu = create_test_pdu(cls.device1)

    def setUp(self):
        super().setUp()
        self.base_url = 'plugins:netbox_pdu_plugin:managedpdu'

    def test_list_view(self):
        self.add_permissions('netbox_pdu_plugin.view_managedpdu')
        url = self._get_url('list')
        response = self.client.get(url)
        self.assertHttpStatus(response, 200)

    def test_list_view_without_permission(self):
        with disable_warnings('django.request'):
            url = self._get_url('list')
            response = self.client.get(url)
            self.assertHttpStatus(response, 403)

    def test_detail_view(self):
        self.add_permissions('netbox_pdu_plugin.view_managedpdu')
        url = self._get_url('detail', self.pdu)
        response = self.client.get(url)
        self.assertHttpStatus(response, 200)
        self.assertEqual(response.context['object'], self.pdu)

    def test_add_view_get(self):
        self.add_permissions('netbox_pdu_plugin.add_managedpdu')
        url = self._get_url('add')
        response = self.client.get(url)
        self.assertHttpStatus(response, 200)

    def test_add_view_post(self):
        # Use superuser to bypass ObjectPermission and form field restrictions.
        superuser = self.create_test_user(username='superuser_add', is_superuser=True)
        self.client.force_login(superuser)
        url = self._get_url('add')
        form_data = self.post_data({
            'device': self.device2,
            'vendor': VendorChoices.RARITAN,
            'api_url': 'https://new.example.com',
            'api_username': 'admin',
            'api_password': 'secret',
            'verify_ssl': False,
        })
        response = self.client.post(url, form_data, follow=True)
        self.assertHttpStatus(response, 200)
        self.assertTrue(ManagedPDU.objects.filter(device=self.device2).exists())

    def test_edit_view(self):
        superuser = self.create_test_user(username='superuser_edit', is_superuser=True)
        self.client.force_login(superuser)
        url = self._get_url('edit', self.pdu)
        form_data = self.post_data({
            'device': self.device1,
            'vendor': VendorChoices.RARITAN,
            'api_url': 'https://edited.example.com',
            'api_username': 'admin',
            'api_password': 'secret',
            'verify_ssl': False,
        })
        response = self.client.post(url, form_data, follow=True)
        self.assertHttpStatus(response, 200)
        self.pdu.refresh_from_db()
        self.assertEqual(self.pdu.api_url, 'https://edited.example.com')

    def test_delete_view(self):
        superuser = self.create_test_user(username='superuser_del', is_superuser=True)
        self.client.force_login(superuser)
        pdu = create_test_pdu(self.device3)
        url = self._get_url('delete', pdu)
        response = self.client.post(url, {'confirm': True}, follow=True)
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
            outlet_name='Outlet 1',
        )

    def setUp(self):
        super().setUp()
        self.base_url = 'plugins:netbox_pdu_plugin:pduoutlet'

    def test_list_view(self):
        self.add_permissions('netbox_pdu_plugin.view_pduoutlet')
        url = self._get_url('list')
        response = self.client.get(url)
        self.assertHttpStatus(response, 200)

    def test_detail_view(self):
        self.add_permissions('netbox_pdu_plugin.view_pduoutlet')
        url = self._get_url('detail', self.outlet)
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
            inlet_name='Inlet 1',
        )

    def setUp(self):
        super().setUp()
        self.base_url = 'plugins:netbox_pdu_plugin:pduinlet'

    def test_list_view(self):
        self.add_permissions('netbox_pdu_plugin.view_pduinlet')
        url = self._get_url('list')
        response = self.client.get(url)
        self.assertHttpStatus(response, 200)

    def test_detail_view(self):
        self.add_permissions('netbox_pdu_plugin.view_pduinlet')
        url = self._get_url('detail', self.inlet)
        response = self.client.get(url)
        self.assertHttpStatus(response, 200)
