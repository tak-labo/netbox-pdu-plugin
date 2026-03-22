"""
Unit tests for the UniFi PDU backend.

All external communication is mocked with unittest.mock.
Tests run without Django or a real UniFi controller.
"""
import unittest
from unittest.mock import MagicMock, patch

import requests

from netbox_pdu_plugin.backends.base import PDUClientError
from netbox_pdu_plugin.backends.unifi import UniFiPDUClient


def _make_client(username='admin', password='secret', base_url='https://unifi.example.com', **kwargs):
    """Create a test client with a mocked requests.Session."""
    with patch('netbox_pdu_plugin.backends.unifi.requests.Session') as mock_session_cls:
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session
        client = UniFiPDUClient(
            base_url=base_url,
            username=username,
            password=password,
            verify_ssl=False,
            **kwargs,
        )
        client.session = mock_session
    return client


def _ok_response(data=None, status_code=200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = {'data': data} if data is not None else {}
    resp.raise_for_status = MagicMock()
    return resp


# ---------------------------------------------------------------------------
# _parse_outlet() tests (static method)
# ---------------------------------------------------------------------------

class TestParseOutlet(unittest.TestCase):

    def test_on_state(self):
        o = {'index': 1, 'name': 'Outlet 1', 'relay_state': True,
             'outlet_current': 1.5, 'outlet_power': 300.0, 'outlet_voltage': 100.0,
             'outlet_power_factor': 0.99}
        result = UniFiPDUClient._parse_outlet(o)
        self.assertEqual(result['outlet_number'], 1)
        self.assertEqual(result['switchingState'], 'on')
        self.assertEqual(result['current_a'], 1.5)
        self.assertEqual(result['power_w'], 300.0)
        self.assertEqual(result['voltage_v'], 100.0)
        self.assertEqual(result['power_factor'], 0.99)

    def test_off_state(self):
        o = {'index': 2, 'name': 'Outlet 2', 'relay_state': False}
        result = UniFiPDUClient._parse_outlet(o)
        self.assertEqual(result['switchingState'], 'off')

    def test_missing_sensor_values_become_none(self):
        o = {'index': 3, 'relay_state': True}
        result = UniFiPDUClient._parse_outlet(o)
        self.assertIsNone(result['current_a'])
        self.assertIsNone(result['power_w'])
        self.assertIsNone(result['voltage_v'])
        self.assertIsNone(result['power_factor'])

    def test_invalid_sensor_value_becomes_none(self):
        o = {'index': 1, 'relay_state': True, 'outlet_current': 'N/A'}
        result = UniFiPDUClient._parse_outlet(o)
        self.assertIsNone(result['current_a'])

    def test_energy_fields_are_none(self):
        """UniFi does not return cumulative energy data."""
        o = {'index': 1, 'relay_state': True}
        result = UniFiPDUClient._parse_outlet(o)
        self.assertIsNone(result['energy_wh'])
        self.assertIsNone(result['energy_reset_epoch'])


# ---------------------------------------------------------------------------
# _login() tests
# ---------------------------------------------------------------------------

class TestLogin(unittest.TestCase):

    def test_api_key_udm_prefix_on_health_200(self):
        """API key mode uses UDM prefix when /stat/health returns 200."""
        client = _make_client(username='', password='MY_API_KEY')
        client.session.headers = {}

        health_resp = _ok_response()
        health_resp.status_code = 200
        client.session.get.return_value = health_resp

        client._login()

        # X-API-KEY header is set
        self.assertEqual(client.session.headers.get('X-API-KEY'), 'MY_API_KEY')
        # UDM prefix is used
        self.assertIn('/proxy/network/api/s/', client._api_prefix)

    def test_api_key_fallback_to_standalone_prefix(self):
        """API key mode falls back to standalone prefix when UDM health check fails."""
        client = _make_client(username='', password='MY_API_KEY')
        client.session.headers = {}

        fail_resp = _ok_response()
        fail_resp.status_code = 404
        success_resp = _ok_response()
        success_resp.status_code = 200
        client.session.get.side_effect = [fail_resp, success_resp]

        client._login()

        self.assertIn('/api/s/', client._api_prefix)
        self.assertNotIn('/proxy', client._api_prefix)

    def test_api_key_both_fail_uses_default_udm(self):
        """API key mode uses default UDM prefix when both health checks fail."""
        client = _make_client(username='', password='MY_API_KEY')
        client.session.headers = {}

        fail_resp = _ok_response()
        fail_resp.status_code = 503
        client.session.get.return_value = fail_resp

        client._login()

        self.assertIn('/proxy/network/api/s/', client._api_prefix)

    def test_session_login_udm_success(self):
        """Session login succeeds via UDM endpoint."""
        client = _make_client(username='admin', password='secret')

        ok_resp = _ok_response()
        ok_resp.status_code = 200
        client.session.post.return_value = ok_resp

        client._login()

        self.assertIn('/proxy/network/api/s/', client._api_prefix)

    def test_session_login_standalone_fallback(self):
        """Falls back to standalone login when UDM login fails."""
        client = _make_client(username='admin', password='secret')

        fail_resp = _ok_response()
        fail_resp.status_code = 401
        ok_resp = _ok_response()
        ok_resp.status_code = 200
        client.session.post.side_effect = [fail_resp, ok_resp]

        client._login()

        self.assertIn('/api/s/', client._api_prefix)
        self.assertNotIn('/proxy', client._api_prefix)

    def test_both_login_paths_fail_raises(self):
        """Raises PDUClientError when both login paths fail."""
        client = _make_client(username='admin', password='wrong')

        fail_resp = _ok_response()
        fail_resp.status_code = 401
        client.session.post.return_value = fail_resp

        with self.assertRaises(PDUClientError) as ctx:
            client._login()
        self.assertIn('Failed to authenticate', str(ctx.exception))

    def test_login_not_called_twice(self):
        """Skips re-login when _api_prefix is already set."""
        client = _make_client(username='', password='KEY')
        client.session.headers = {}
        client._api_prefix = 'https://unifi.example.com/proxy/network/api/s/default/'

        client._login()

        # Neither get nor post should be called
        client.session.get.assert_not_called()
        client.session.post.assert_not_called()

    def test_site_parsed_from_url(self):
        """Extracts site name from URL path."""
        client = _make_client(
            username='', password='KEY',
            base_url='https://unifi.example.com/s/mysite',
        )
        self.assertEqual(client._site, 'mysite')

    def test_default_site_when_no_path(self):
        """Defaults to 'default' when URL has no /s/<site>."""
        client = _make_client(username='', password='KEY')
        self.assertEqual(client._site, 'default')

    def test_session_login_request_exception_fallback(self):
        """Falls back to standalone when UDM login raises RequestException."""
        client = _make_client(username='admin', password='secret')

        ok_resp = _ok_response()
        ok_resp.status_code = 200
        client.session.post.side_effect = [
            requests.exceptions.ConnectionError('refused'),  # UDM fails
            ok_resp,  # Standalone succeeds
        ]

        client._login()

        self.assertIn('/api/s/', client._api_prefix)
        self.assertNotIn('/proxy', client._api_prefix)

    def test_api_key_request_exception_fallback(self):
        """API key mode falls back when first health check raises RequestException."""
        client = _make_client(username='', password='MY_API_KEY')
        client.session.headers = {}

        ok_resp = _ok_response()
        ok_resp.status_code = 200
        client.session.get.side_effect = [
            requests.exceptions.Timeout(),  # UDM health check fails
            ok_resp,  # Standalone health check succeeds
        ]

        client._login()

        self.assertIn('/api/s/', client._api_prefix)
        self.assertNotIn('/proxy', client._api_prefix)


# ---------------------------------------------------------------------------
# _get_outlet_overrides() tests
# ---------------------------------------------------------------------------

class TestGetOutletOverrides(unittest.TestCase):

    def _make_device(self):
        return {
            '_id': 'device123',
            'outlet_table': [
                {'index': 1, 'name': 'Out1', 'relay_state': True, 'cycle_enabled': False},
                {'index': 2, 'name': 'Out2', 'relay_state': False, 'cycle_enabled': False},
                {'index': 3, 'name': 'Out3', 'relay_state': True, 'cycle_enabled': False},
            ],
            'outlet_overrides': [
                {'index': 1, 'name': 'Custom1', 'relay_state': True, 'cycle_enabled': False},
            ],
        }

    def test_all_outlets_are_included(self):
        """Returns overrides for all outlets even when only some exist."""
        client = _make_client()
        client._get_device = MagicMock(return_value=self._make_device())

        overrides = client._get_outlet_overrides()

        indices = [o['index'] for o in overrides]
        self.assertEqual(sorted(indices), [1, 2, 3])

    def test_existing_override_name_is_preserved(self):
        """Existing outlet_overrides name takes priority."""
        client = _make_client()
        client._get_device = MagicMock(return_value=self._make_device())

        overrides = client._get_outlet_overrides()
        outlet1 = next(o for o in overrides if o['index'] == 1)
        self.assertEqual(outlet1['name'], 'Custom1')

    def test_missing_override_uses_outlet_table_values(self):
        """Outlets without overrides use outlet_table values."""
        client = _make_client()
        client._get_device = MagicMock(return_value=self._make_device())

        overrides = client._get_outlet_overrides()
        outlet2 = next(o for o in overrides if o['index'] == 2)
        self.assertEqual(outlet2['name'], 'Out2')
        self.assertFalse(outlet2['relay_state'])


# ---------------------------------------------------------------------------
# set_outlet_power_state() tests
# ---------------------------------------------------------------------------

class TestSetOutletPowerState(unittest.TestCase):

    def _make_device(self, num_outlets=3):
        return {
            '_id': 'device123',
            'outlet_table': [
                {'index': i, 'name': f'Outlet {i}', 'relay_state': True, 'cycle_enabled': False}
                for i in range(1, num_outlets + 1)
            ],
            'outlet_overrides': [],
        }

    def setUp(self):
        self.client = _make_client()
        self.device = self._make_device()
        self.client._get_device = MagicMock(return_value=self.device)
        self.client._put = MagicMock(return_value={})

    def test_on_sets_relay_state_true(self):
        """'on' sets relay_state to True for the target outlet."""
        self.client.set_outlet_power_state(0, 'on')  # index 0 -> outlet 1

        put_payload = self.client._put.call_args[0][1]
        target = next(o for o in put_payload['outlet_overrides'] if o['index'] == 1)
        self.assertTrue(target['relay_state'])

    def test_off_sets_relay_state_false(self):
        """'off' sets relay_state to False for the target outlet."""
        self.client.set_outlet_power_state(0, 'off')

        put_payload = self.client._put.call_args[0][1]
        target = next(o for o in put_payload['outlet_overrides'] if o['index'] == 1)
        self.assertFalse(target['relay_state'])

    def test_all_outlets_sent_on_put(self):
        """PUT sends outlet_overrides for ALL outlets (not just the modified one)."""
        self.client.set_outlet_power_state(0, 'off')

        put_payload = self.client._put.call_args[0][1]
        self.assertEqual(len(put_payload['outlet_overrides']), 3)

    def test_cycle_sends_off_then_on(self):
        """'cycle' sends off then on with two PUT calls."""
        # Deep-copy payloads to avoid reference mutation issues
        import copy
        recorded = []
        self.client._put = MagicMock(side_effect=lambda path, payload: recorded.append(copy.deepcopy(payload)))

        with patch('netbox_pdu_plugin.backends.unifi.time.sleep'):
            self.client.set_outlet_power_state(0, 'cycle')

        self.assertEqual(len(recorded), 2)

        first_target = next(o for o in recorded[0]['outlet_overrides'] if o['index'] == 1)
        second_target = next(o for o in recorded[1]['outlet_overrides'] if o['index'] == 1)

        self.assertFalse(first_target['relay_state'])   # off
        self.assertTrue(second_target['relay_state'])   # on

    def test_invalid_state_raises(self):
        with self.assertRaises(PDUClientError) as ctx:
            self.client.set_outlet_power_state(0, 'reboot')
        self.assertIn('Invalid power state', str(ctx.exception))

    def test_outlet_index_is_1based(self):
        """outlet_index 0 maps to UniFi index 1."""
        self.client.set_outlet_power_state(2, 'on')

        put_payload = self.client._put.call_args[0][1]
        modified_indices = [
            o['index'] for o in put_payload['outlet_overrides']
            if o['relay_state']
        ]
        self.assertIn(3, modified_indices)


# ---------------------------------------------------------------------------
# set_outlet_name() tests
# ---------------------------------------------------------------------------

class TestSetOutletName(unittest.TestCase):

    def _make_device(self):
        return {
            '_id': 'device123',
            'outlet_table': [
                {'index': 1, 'name': 'Outlet 1', 'relay_state': True, 'cycle_enabled': False},
                {'index': 2, 'name': 'Outlet 2', 'relay_state': False, 'cycle_enabled': False},
            ],
            'outlet_overrides': [],
        }

    def setUp(self):
        self.client = _make_client()
        self.client._get_device = MagicMock(return_value=self._make_device())
        self.client._put = MagicMock(return_value={})

    def test_name_is_updated(self):
        self.client.set_outlet_name(0, 'Server-01')

        put_payload = self.client._put.call_args[0][1]
        target = next(o for o in put_payload['outlet_overrides'] if o['index'] == 1)
        self.assertEqual(target['name'], 'Server-01')

    def test_all_outlets_sent(self):
        """All outlets are included in the PUT even when only one name changes."""
        self.client.set_outlet_name(0, 'Server-01')

        put_payload = self.client._put.call_args[0][1]
        self.assertEqual(len(put_payload['outlet_overrides']), 2)


# ---------------------------------------------------------------------------
# get_all_inlet_data() tests
# ---------------------------------------------------------------------------

class TestGetAllInletData(unittest.TestCase):

    def test_returns_total_power_from_device(self):
        """Returns outlet_ac_power_consumption as Inlet 1 power_w."""
        client = _make_client()
        client._get_device = MagicMock(return_value={
            'outlet_ac_power_consumption': 450.5,
        })

        inlets = client.get_all_inlet_data()

        self.assertEqual(len(inlets), 1)
        self.assertEqual(inlets[0]['inlet_number'], 1)
        self.assertEqual(inlets[0]['power_w'], 450.5)

    def test_other_fields_are_none(self):
        """UniFi does not provide current, voltage, or frequency for inlets."""
        client = _make_client()
        client._get_device = MagicMock(return_value={'outlet_ac_power_consumption': 100})

        inlets = client.get_all_inlet_data()
        self.assertIsNone(inlets[0]['current_a'])
        self.assertIsNone(inlets[0]['voltage_v'])
        self.assertIsNone(inlets[0]['frequency_hz'])

    def test_handles_missing_consumption(self):
        """Returns 0.0 when outlet_ac_power_consumption is absent."""
        client = _make_client()
        client._get_device = MagicMock(return_value={})

        inlets = client.get_all_inlet_data()
        self.assertEqual(inlets[0]['power_w'], 0.0)

    def test_set_inlet_name_raises(self):
        """set_inlet_name is not supported for UniFi."""
        client = _make_client()
        with self.assertRaises(PDUClientError) as ctx:
            client.set_inlet_name(0, 'Main Input')
        self.assertIn('not supported', str(ctx.exception))


# ---------------------------------------------------------------------------
# _get_device() tests
# ---------------------------------------------------------------------------

class TestGetDevice(unittest.TestCase):

    def _setup_device_list(self, client, devices):
        client._api_prefix = 'https://unifi.example.com/api/s/default/'
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {'data': devices}
        resp.raise_for_status = MagicMock()
        client.session.get.return_value = resp

    def test_no_pdu_device_raises(self):
        """Raises PDUClientError when no device has outlet_table."""
        client = _make_client()
        self._setup_device_list(client, [{'mac': 'aa:bb:cc:dd:ee:ff'}])  # No outlet_table

        with self.assertRaises(PDUClientError) as ctx:
            client._get_device()
        self.assertIn('No PDU device', str(ctx.exception))

    def test_matches_by_mac_address(self):
        """Selects the device matching pdu_mac_address."""
        mock_managed_pdu = MagicMock()
        mock_managed_pdu.pdu_mac_address = 'AA:BB:CC:DD:EE:FF'
        mock_managed_pdu.device.name = 'pdu-01'

        client = _make_client(managed_pdu=mock_managed_pdu)
        devices = [
            {'mac': 'aa:bb:cc:dd:ee:ff', 'outlet_table': [{}], 'name': 'pdu-01'},
            {'mac': '11:22:33:44:55:66', 'outlet_table': [{}], 'name': 'pdu-02'},
        ]
        self._setup_device_list(client, devices)

        device = client._get_device()
        self.assertEqual(device['mac'], 'aa:bb:cc:dd:ee:ff')

    def test_matches_by_name_when_no_mac(self):
        """Falls back to NetBox device.name when MAC is not set."""
        mock_managed_pdu = MagicMock()
        mock_managed_pdu.pdu_mac_address = ''
        mock_managed_pdu.device.name = 'pdu-02'

        client = _make_client(managed_pdu=mock_managed_pdu)
        devices = [
            {'mac': 'aa:bb:cc:dd:ee:ff', 'outlet_table': [{}], 'name': 'pdu-01'},
            {'mac': '11:22:33:44:55:66', 'outlet_table': [{}], 'name': 'pdu-02'},
        ]
        self._setup_device_list(client, devices)

        device = client._get_device()
        self.assertEqual(device['name'], 'pdu-02')

    def test_returns_first_when_no_match(self):
        """Returns the first PDU device when neither MAC nor name matches."""
        client = _make_client()  # No managed_pdu
        devices = [
            {'mac': 'aa:bb:cc', 'outlet_table': [{}], 'name': 'pdu-x'},
            {'mac': 'dd:ee:ff', 'outlet_table': [{}], 'name': 'pdu-y'},
        ]
        self._setup_device_list(client, devices)

        device = client._get_device()
        self.assertEqual(device['name'], 'pdu-x')

    def test_device_is_cached(self):
        """Does not call session.get on subsequent calls (uses cache)."""
        client = _make_client()
        cached = {'mac': 'aa:bb', 'outlet_table': [{}]}
        client._device_cache = cached

        device = client._get_device()
        client.session.get.assert_not_called()
        self.assertIs(device, cached)


# ---------------------------------------------------------------------------
# get_pdu_info() tests
# ---------------------------------------------------------------------------

class TestGetPduInfo(unittest.TestCase):

    def test_basic_info(self):
        client = _make_client()
        client._get_device = MagicMock(return_value={
            'model': 'USP-PDU-Pro',
            'serial': 'SN123456',
            'version': '7.1.66',
            'mac': 'aa:bb:cc:dd:ee:ff',
            'ip': '192.168.1.50',
            'outlet_ac_power_budget': 1920,
        })
        info = client.get_pdu_info()
        self.assertEqual(info['model'], 'USP-PDU-Pro')
        self.assertEqual(info['serial_number'], 'SN123456')
        self.assertEqual(info['firmware_version'], '7.1.66')
        self.assertEqual(info['pdu_mac_address'], 'aa:bb:cc:dd:ee:ff')
        self.assertEqual(info['rated_power'], '1920 W')

    def test_network_interface_generated(self):
        client = _make_client()
        client._get_device = MagicMock(return_value={
            'mac': 'aa:bb:cc:dd:ee:ff',
            'ip': '10.0.0.1',
        })
        info = client.get_pdu_info()
        self.assertEqual(len(info['network_interfaces']), 1)
        iface = info['network_interfaces'][0]
        self.assertEqual(iface['mac_address'], 'aa:bb:cc:dd:ee:ff')
        self.assertEqual(iface['ip_address'], '10.0.0.1')

    def test_no_mac_no_interface(self):
        """No network interface generated when MAC is absent."""
        client = _make_client()
        client._get_device = MagicMock(return_value={})
        info = client.get_pdu_info()
        self.assertEqual(info['network_interfaces'], [])

    def test_no_budget_empty_rated_power(self):
        """rated_power is empty string when outlet_ac_power_budget is absent."""
        client = _make_client()
        client._get_device = MagicMock(return_value={'mac': ''})
        info = client.get_pdu_info()
        self.assertEqual(info['rated_power'], '')


# ---------------------------------------------------------------------------
# get_all_outlet_data() / get_single_outlet_data() tests
# ---------------------------------------------------------------------------

class TestGetAllOutletData(unittest.TestCase):

    def test_returns_parsed_outlets(self):
        client = _make_client()
        client._get_device = MagicMock(return_value={
            'outlet_table': [
                {'index': 1, 'name': 'Out1', 'relay_state': True,
                 'outlet_current': 1.0, 'outlet_power': 100, 'outlet_voltage': 100, 'outlet_power_factor': 0.99},
                {'index': 2, 'name': 'Out2', 'relay_state': False},
            ],
        })
        result = client.get_all_outlet_data()
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]['switchingState'], 'on')
        self.assertEqual(result[1]['switchingState'], 'off')

    def test_empty_outlet_table_raises(self):
        client = _make_client()
        client._get_device = MagicMock(return_value={'outlet_table': []})
        with self.assertRaises(PDUClientError) as ctx:
            client.get_all_outlet_data()
        self.assertIn('No outlets', str(ctx.exception))

    def test_missing_outlet_table_raises(self):
        client = _make_client()
        client._get_device = MagicMock(return_value={})
        with self.assertRaises(PDUClientError):
            client.get_all_outlet_data()


class TestGetSingleOutletData(unittest.TestCase):

    def test_returns_correct_outlet(self):
        client = _make_client()
        client._get_device = MagicMock(return_value={
            'outlet_table': [
                {'index': 1, 'relay_state': True},
                {'index': 2, 'relay_state': False},
            ],
        })
        result = client.get_single_outlet_data(1)
        self.assertEqual(result['outlet_number'], 2)
        self.assertEqual(result['switchingState'], 'off')

    def test_out_of_range_raises(self):
        client = _make_client()
        client._get_device = MagicMock(return_value={
            'outlet_table': [{'index': 1, 'relay_state': True}],
        })
        with self.assertRaises(PDUClientError) as ctx:
            client.get_single_outlet_data(5)
        self.assertIn('out of range', str(ctx.exception))


# ---------------------------------------------------------------------------
# get_single_inlet_data() tests
# ---------------------------------------------------------------------------

class TestGetSingleInletData(unittest.TestCase):

    def test_returns_inlet(self):
        client = _make_client()
        client._get_device = MagicMock(return_value={'outlet_ac_power_consumption': 200})
        result = client.get_single_inlet_data(0)
        self.assertEqual(result['inlet_number'], 1)
        self.assertEqual(result['power_w'], 200.0)

    def test_out_of_range_raises(self):
        client = _make_client()
        client._get_device = MagicMock(return_value={})
        with self.assertRaises(PDUClientError) as ctx:
            client.get_single_inlet_data(1)
        self.assertIn('out of range', str(ctx.exception))


# ---------------------------------------------------------------------------
# _get() / _put() HTTP error handling tests
# ---------------------------------------------------------------------------

class TestHttpHelpers(unittest.TestCase):

    def _setup_client(self):
        client = _make_client()
        client._api_prefix = 'https://unifi.example.com/api/s/default/'
        return client

    def test_get_ssl_error(self):
        client = self._setup_client()
        client.session.get.side_effect = requests.exceptions.SSLError('cert failed')
        with self.assertRaises(PDUClientError) as ctx:
            client._get('stat/device')
        self.assertIn('SSL error', str(ctx.exception))

    def test_get_connection_error(self):
        client = self._setup_client()
        client.session.get.side_effect = requests.exceptions.ConnectionError('refused')
        with self.assertRaises(PDUClientError) as ctx:
            client._get('stat/device')
        self.assertIn('Connection error', str(ctx.exception))

    def test_get_timeout(self):
        client = self._setup_client()
        client.session.get.side_effect = requests.exceptions.Timeout()
        with self.assertRaises(PDUClientError) as ctx:
            client._get('stat/device')
        self.assertIn('timed out', str(ctx.exception))

    def test_get_http_error(self):
        client = self._setup_client()
        resp = MagicMock()
        resp.status_code = 403
        resp.raise_for_status.side_effect = requests.exceptions.HTTPError('403 Forbidden')
        client.session.get.return_value = resp
        with self.assertRaises(PDUClientError) as ctx:
            client._get('stat/device')
        self.assertIn('HTTP error', str(ctx.exception))

    def test_get_json_parse_error(self):
        client = self._setup_client()
        resp = MagicMock()
        resp.status_code = 200
        resp.raise_for_status = MagicMock()
        resp.json.side_effect = ValueError('No JSON')
        client.session.get.return_value = resp
        with self.assertRaises(PDUClientError) as ctx:
            client._get('stat/device')
        self.assertIn('JSON parse error', str(ctx.exception))

    def test_put_ssl_error(self):
        client = self._setup_client()
        client.session.put.side_effect = requests.exceptions.SSLError('cert')
        with self.assertRaises(PDUClientError):
            client._put('rest/device/x', {'key': 'val'})

    def test_put_timeout(self):
        client = self._setup_client()
        client.session.put.side_effect = requests.exceptions.Timeout()
        with self.assertRaises(PDUClientError):
            client._put('rest/device/x', {})

    def test_get_returns_data_field(self):
        """Returns the 'data' field from a successful response."""
        client = self._setup_client()
        resp = _ok_response(data=[{'mac': 'aa:bb'}])
        client.session.get.return_value = resp
        result = client._get('stat/device')
        self.assertEqual(result, [{'mac': 'aa:bb'}])


# ---------------------------------------------------------------------------
# get_outlet_power_state_by_index() tests
# ---------------------------------------------------------------------------

class TestGetOutletPowerStateByIndex(unittest.TestCase):

    def _make_device(self, relay_states):
        return {
            'outlet_table': [
                {'index': i + 1, 'relay_state': state}
                for i, state in enumerate(relay_states)
            ],
        }

    def test_returns_on(self):
        client = _make_client()
        client._device_cache = 'force_invalidate'
        client._get_device = MagicMock(return_value=self._make_device([True, False]))
        result = client.get_outlet_power_state_by_index(0)
        self.assertEqual(result, 'on')

    def test_returns_off(self):
        client = _make_client()
        client._device_cache = 'x'
        client._get_device = MagicMock(return_value=self._make_device([True, False]))
        result = client.get_outlet_power_state_by_index(1)
        self.assertEqual(result, 'off')

    def test_returns_unknown_for_missing_outlet(self):
        client = _make_client()
        client._device_cache = 'x'
        client._get_device = MagicMock(return_value=self._make_device([True]))
        result = client.get_outlet_power_state_by_index(5)  # index 6 doesn't exist
        self.assertEqual(result, 'unknown')

    def test_invalidates_cache(self):
        """Cache is invalidated before fetching device data."""
        client = _make_client()
        client._device_cache = {'outlet_table': [{'index': 1, 'relay_state': True}]}
        client._api_prefix = 'https://unifi.example.com/api/s/default/'
        resp = _ok_response(data=[{'outlet_table': [{'index': 1, 'relay_state': True}]}])
        client.session.get.return_value = resp
        client.get_outlet_power_state_by_index(0)
        # After cache reset, _get_device makes an API call
        client.session.get.assert_called_once()


if __name__ == '__main__':
    unittest.main()
