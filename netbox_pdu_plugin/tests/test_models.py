"""
Test cases for NetBox PDU Plugin models.

Run inside Docker:
  docker compose exec netbox python manage.py test netbox_pdu_plugin.tests.test_models -v2
"""

from dcim.models import Device, DeviceRole, DeviceType, Manufacturer, Site
from django.db import IntegrityError
from django.test import TestCase

from ..choices import OutletStatusChoices, SyncStatusChoices, VendorChoices
from ..models import ManagedPDU, PDUInlet, PDUNetworkInterface, PDUOutlet


def create_test_device(name: str = 'Test PDU') -> Device:
    """Create a minimal Device for use in ManagedPDU tests."""
    manufacturer, _ = Manufacturer.objects.get_or_create(name='Test Mfr', slug='test-mfr')
    device_type, _ = DeviceType.objects.get_or_create(
        manufacturer=manufacturer,
        model='Test Model',
        defaults={'slug': 'test-model'},
    )
    role, _ = DeviceRole.objects.get_or_create(name='PDU', defaults={'slug': 'pdu', 'color': 'aa1409'})
    site, _ = Site.objects.get_or_create(name='Test Site', defaults={'slug': 'test-site'})
    return Device.objects.create(
        name=name,
        device_type=device_type,
        role=role,
        site=site,
    )


def create_test_pdu(device: Device | None = None, **kwargs) -> ManagedPDU:
    """Create a ManagedPDU with sensible defaults."""
    if device is None:
        device = create_test_device()
    defaults = {
        'vendor': VendorChoices.RARITAN,
        'api_url': 'https://pdu.example.com',
        'api_username': 'admin',
        'api_password': 'secret',
        'verify_ssl': False,
    }
    defaults.update(kwargs)
    return ManagedPDU.objects.create(device=device, **defaults)


class ManagedPDUModelTest(TestCase):
    """Tests for the ManagedPDU model."""

    @classmethod
    def setUpTestData(cls):
        cls.device = create_test_device('PDU-1')
        cls.pdu = create_test_pdu(cls.device)

    def test_str(self):
        self.assertIn('PDU', str(self.pdu))

    def test_get_absolute_url(self):
        url = self.pdu.get_absolute_url()
        self.assertIn(str(self.pdu.pk), url)

    def test_get_sync_status_color_never(self):
        self.pdu.sync_status = SyncStatusChoices.NEVER
        color = self.pdu.get_sync_status_color()
        self.assertIsNotNone(color)

    def test_get_sync_status_color_success(self):
        self.pdu.sync_status = SyncStatusChoices.SUCCESS
        color = self.pdu.get_sync_status_color()
        self.assertIsNotNone(color)

    def test_device_one_to_one(self):
        """A device can have at most one ManagedPDU."""
        with self.assertRaises(IntegrityError):
            create_test_pdu(self.device)

    def test_vendor_default(self):
        self.assertEqual(self.pdu.vendor, VendorChoices.RARITAN)

    def test_sync_status_default(self):
        self.assertEqual(self.pdu.sync_status, SyncStatusChoices.NEVER)


class PDUOutletModelTest(TestCase):
    """Tests for the PDUOutlet model."""

    @classmethod
    def setUpTestData(cls):
        cls.pdu = create_test_pdu()
        cls.outlet = PDUOutlet.objects.create(
            managed_pdu=cls.pdu,
            outlet_number=1,
            outlet_name='Outlet 1',
            status=OutletStatusChoices.ON,
            power_w=100.0,
            voltage_v=200.0,
            current_a=0.5,
        )

    def test_str(self):
        self.assertIn('1', str(self.outlet))

    def test_get_absolute_url(self):
        url = self.outlet.get_absolute_url()
        self.assertIn(str(self.outlet.pk), url)

    def test_get_status_color(self):
        color = self.outlet.get_status_color()
        self.assertIsNotNone(color)

    def test_unique_outlet_number_per_pdu(self):
        """Outlet numbers must be unique within a PDU."""
        with self.assertRaises(IntegrityError):
            PDUOutlet.objects.create(
                managed_pdu=self.pdu,
                outlet_number=1,
            )

    def test_outlet_number_reusable_across_pdus(self):
        """Same outlet number can exist on different PDUs."""
        other_pdu = create_test_pdu(create_test_device('PDU-2'))
        outlet = PDUOutlet.objects.create(
            managed_pdu=other_pdu,
            outlet_number=1,
        )
        self.assertEqual(outlet.outlet_number, 1)


class PDUInletModelTest(TestCase):
    """Tests for the PDUInlet model."""

    @classmethod
    def setUpTestData(cls):
        cls.pdu = create_test_pdu()
        cls.inlet = PDUInlet.objects.create(
            managed_pdu=cls.pdu,
            inlet_number=1,
            inlet_name='Inlet 1',
            power_w=500.0,
            voltage_v=200.0,
            current_a=2.5,
        )

    def test_str(self):
        self.assertIn('1', str(self.inlet))

    def test_get_absolute_url(self):
        url = self.inlet.get_absolute_url()
        self.assertIn(str(self.inlet.pk), url)

    def test_unique_inlet_number_per_pdu(self):
        """Inlet numbers must be unique within a PDU."""
        with self.assertRaises(IntegrityError):
            PDUInlet.objects.create(
                managed_pdu=self.pdu,
                inlet_number=1,
            )


class PDUNetworkInterfaceModelTest(TestCase):
    """Tests for the PDUNetworkInterface model."""

    @classmethod
    def setUpTestData(cls):
        cls.pdu = create_test_pdu()
        cls.nic = PDUNetworkInterface.objects.create(
            managed_pdu=cls.pdu,
            interface_name='ETH1',
            mac_address='00:11:22:33:44:55',
            ip_address='192.168.1.100',
        )

    def test_str(self):
        self.assertIn('ETH1', str(self.nic))

    def test_unique_interface_per_pdu(self):
        """Interface names must be unique within a PDU."""
        with self.assertRaises(IntegrityError):
            PDUNetworkInterface.objects.create(
                managed_pdu=self.pdu,
                interface_name='ETH1',
            )
