"""
Tests for the get_pdu_client() factory function.

Verifies that the correct backend class is returned for each vendor
and that unknown vendors raise an error.
"""
import unittest
from unittest.mock import MagicMock, patch

from netbox_pdu_plugin.backends import _VENDOR_BACKENDS, get_pdu_client
from netbox_pdu_plugin.backends.base import PDUClientError
from netbox_pdu_plugin.backends.raritan import RaritanPDUClient
from netbox_pdu_plugin.backends.unifi import UniFiPDUClient


def _mock_managed_pdu(vendor, api_url='https://pdu.example.com',
                       api_username='admin', api_password='secret',
                       verify_ssl=True):
    """Create a mock ManagedPDU model object."""
    pdu = MagicMock()
    pdu.vendor = vendor
    pdu.api_url = api_url
    pdu.api_username = api_username
    pdu.api_password = api_password
    pdu.verify_ssl = verify_ssl
    return pdu


class TestGetPduClientFactory(unittest.TestCase):

    def test_raritan_returns_raritan_client(self):
        """vendor='raritan' returns RaritanPDUClient."""
        managed_pdu = _mock_managed_pdu('raritan')
        with patch('netbox_pdu_plugin.backends.raritan.requests.Session'):
            client = get_pdu_client(managed_pdu)
        self.assertIsInstance(client, RaritanPDUClient)

    def test_ubiquiti_returns_unifi_client(self):
        """vendor='ubiquiti' returns UniFiPDUClient."""
        managed_pdu = _mock_managed_pdu('ubiquiti')
        with patch('netbox_pdu_plugin.backends.unifi.requests.Session'):
            client = get_pdu_client(managed_pdu)
        self.assertIsInstance(client, UniFiPDUClient)

    def test_unknown_vendor_raises(self):
        """Unregistered vendor raises PDUClientError."""
        managed_pdu = _mock_managed_pdu('fakevendor')
        with self.assertRaises(PDUClientError) as ctx:
            get_pdu_client(managed_pdu)
        self.assertIn('fakevendor', str(ctx.exception))

    def test_client_receives_correct_credentials(self):
        """Client receives the correct credentials from ManagedPDU."""
        managed_pdu = _mock_managed_pdu(
            'raritan',
            api_url='https://192.168.1.100',
            api_username='user1',
            api_password='pass1',
            verify_ssl=False,
        )
        with patch('netbox_pdu_plugin.backends.raritan.requests.Session'):
            client = get_pdu_client(managed_pdu)
        self.assertEqual(client.base_url, 'https://192.168.1.100')
        self.assertEqual(client.username, 'user1')
        self.assertEqual(client.password, 'pass1')
        self.assertFalse(client.verify_ssl)

    def test_managed_pdu_is_passed_to_unifi_client(self):
        """managed_pdu is passed to UniFi client for device identification."""
        managed_pdu = _mock_managed_pdu('ubiquiti')
        with patch('netbox_pdu_plugin.backends.unifi.requests.Session'):
            client = get_pdu_client(managed_pdu)
        self.assertIs(client.managed_pdu, managed_pdu)

    def test_all_registered_vendors_can_be_instantiated(self):
        """All vendors in _VENDOR_BACKENDS can be instantiated."""
        for vendor_key in _VENDOR_BACKENDS:
            managed_pdu = _mock_managed_pdu(vendor_key)
            with patch('netbox_pdu_plugin.backends.raritan.requests.Session'), \
                 patch('netbox_pdu_plugin.backends.unifi.requests.Session'):
                client = get_pdu_client(managed_pdu)
            self.assertIsNotNone(client, f'{vendor_key} client is None')

    def test_api_key_mode_username_empty(self):
        """UniFi client works with empty username (API key mode)."""
        managed_pdu = _mock_managed_pdu('ubiquiti', api_username='', api_password='my_api_key')
        with patch('netbox_pdu_plugin.backends.unifi.requests.Session'):
            client = get_pdu_client(managed_pdu)
        self.assertIsInstance(client, UniFiPDUClient)
        self.assertTrue(client._use_api_key)


if __name__ == '__main__':
    unittest.main()
