"""
Unit tests for the Raritan PDU backend.

All external communication is mocked with unittest.mock,
so tests run without Django or a real PDU device.
"""
import unittest
from unittest.mock import MagicMock, patch

import requests

from netbox_pdu_plugin.backends.base import PDUClientError
from netbox_pdu_plugin.backends.raritan import RaritanPDUClient


def _make_client(**kwargs):
    """Create a test client with a mocked requests.Session."""
    with patch('netbox_pdu_plugin.backends.raritan.requests.Session'):
        client = RaritanPDUClient(
            base_url='https://pdu.example.com',
            username='admin',
            password='secret',
            verify_ssl=False,
            **kwargs,
        )
    return client


# ---------------------------------------------------------------------------
# _rpc() tests
# ---------------------------------------------------------------------------

class TestRpcMethod(unittest.TestCase):
    """Tests for _rpc() success and error paths."""

    def setUp(self):
        self.client = _make_client()

    def _mock_response(self, json_data, status_code=200):
        resp = MagicMock()
        resp.status_code = status_code
        resp.json.return_value = json_data
        resp.raise_for_status = MagicMock()
        return resp

    def test_returns_ret_value_when_present(self):
        """Returns _ret_ value when present in result."""
        resp = self._mock_response({'jsonrpc': '2.0', 'result': {'_ret_': [{'rid': '/tfwopaque/a'}]}, 'id': 1})
        self.client.session.post.return_value = resp

        result = self.client._rpc('/model/pdu/0', 'getOutlets')
        self.assertEqual(result, [{'rid': '/tfwopaque/a'}])

    def test_returns_result_without_ret(self):
        """Returns result as-is when _ret_ is absent."""
        resp = self._mock_response({'jsonrpc': '2.0', 'result': {'powerState': 1}, 'id': 1})
        self.client.session.post.return_value = resp

        result = self.client._rpc('/model/pdu/0/outlet/0', 'getState')
        self.assertEqual(result, {'powerState': 1})

    def test_raises_on_jsonrpc_error(self):
        """Raises PDUClientError when response contains an error field."""
        resp = self._mock_response({
            'jsonrpc': '2.0',
            'error': {'code': -32600, 'message': 'Invalid Request'},
            'id': 1,
        })
        self.client.session.post.return_value = resp

        with self.assertRaises(PDUClientError) as ctx:
            self.client._rpc('/model/pdu/0', 'badMethod')
        self.assertIn('-32600', str(ctx.exception))

    def test_raises_on_http_error(self):
        """Converts HTTP 4xx/5xx to PDUClientError."""
        resp = self._mock_response({}, status_code=401)
        resp.raise_for_status.side_effect = requests.exceptions.HTTPError('401 Unauthorized')
        self.client.session.post.return_value = resp

        with self.assertRaises(PDUClientError) as ctx:
            self.client._rpc('/model/pdu/0', 'getMetaData')
        self.assertIn('HTTP error', str(ctx.exception))

    def test_raises_on_connection_error(self):
        """Converts connection error to PDUClientError."""
        self.client.session.post.side_effect = requests.exceptions.ConnectionError('refused')

        with self.assertRaises(PDUClientError) as ctx:
            self.client._rpc('/model/pdu/0', 'getMetaData')
        self.assertIn('Connection error', str(ctx.exception))

    def test_raises_on_timeout(self):
        """Converts timeout to PDUClientError."""
        self.client.session.post.side_effect = requests.exceptions.Timeout()

        with self.assertRaises(PDUClientError) as ctx:
            self.client._rpc('/model/pdu/0', 'getMetaData')
        self.assertIn('timed out', str(ctx.exception))

    def test_raises_on_ssl_error(self):
        """Converts SSL error to PDUClientError."""
        self.client.session.post.side_effect = requests.exceptions.SSLError('cert verify failed')

        with self.assertRaises(PDUClientError) as ctx:
            self.client._rpc('/model/pdu/0', 'getMetaData')
        self.assertIn('SSL error', str(ctx.exception))

    def test_raises_on_json_parse_error(self):
        """Converts JSON parse error to PDUClientError."""
        resp = MagicMock()
        resp.status_code = 200
        resp.raise_for_status = MagicMock()
        resp.json.side_effect = ValueError('No JSON')
        self.client.session.post.return_value = resp

        with self.assertRaises(PDUClientError) as ctx:
            self.client._rpc('/model/pdu/0', 'getMetaData')
        self.assertIn('JSON parse error', str(ctx.exception))

    def test_rpc_id_increments(self):
        """Request ID increments with each call."""
        resp = MagicMock()
        resp.status_code = 200
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {'jsonrpc': '2.0', 'result': None, 'id': 1}
        self.client.session.post.return_value = resp

        self.client._rpc('/model/pdu/0', 'method1')
        self.client._rpc('/model/pdu/0', 'method2')

        calls = self.client.session.post.call_args_list
        id1 = calls[0][1]['json']['id']
        id2 = calls[1][1]['json']['id']
        self.assertGreater(id2, id1)


# ---------------------------------------------------------------------------
# _power_state_str() tests
# ---------------------------------------------------------------------------

class TestPowerStateStr(unittest.TestCase):

    def setUp(self):
        self.client = _make_client()

    def test_on(self):
        self.assertEqual(self.client._power_state_str(1), 'on')

    def test_off(self):
        self.assertEqual(self.client._power_state_str(0), 'off')

    def test_unknown_for_other_values(self):
        self.assertEqual(self.client._power_state_str(2), 'unknown')
        self.assertEqual(self.client._power_state_str(None), 'unknown')
        self.assertEqual(self.client._power_state_str('on'), 'unknown')


# ---------------------------------------------------------------------------
# get_outlet_power_state_by_index() tests
# ---------------------------------------------------------------------------

class TestGetOutletPowerState(unittest.TestCase):

    def setUp(self):
        self.client = _make_client()

    def test_returns_on(self):
        self.client._rpc = MagicMock(return_value={'powerState': 1})
        self.assertEqual(self.client.get_outlet_power_state_by_index(0), 'on')

    def test_returns_off(self):
        self.client._rpc = MagicMock(return_value={'powerState': 0})
        self.assertEqual(self.client.get_outlet_power_state_by_index(0), 'off')

    def test_returns_unknown_when_none(self):
        self.client._rpc = MagicMock(return_value=None)
        self.assertEqual(self.client.get_outlet_power_state_by_index(0), 'unknown')

    def test_uses_correct_path(self):
        """Verifies the 0-based outlet_index is used in the RPC path."""
        self.client._rpc = MagicMock(return_value={'powerState': 1})
        self.client.get_outlet_power_state_by_index(3)
        path = self.client._rpc.call_args[0][0]
        self.assertIn('/3', path)


# ---------------------------------------------------------------------------
# set_outlet_power_state() tests
# ---------------------------------------------------------------------------

class TestSetOutletPowerState(unittest.TestCase):

    def setUp(self):
        self.client = _make_client()
        self.client._rpc = MagicMock(return_value=None)

    def test_on_calls_setPowerState_with_pstate_1(self):
        self.client.set_outlet_power_state(0, 'on')
        self.client._rpc.assert_called_once_with(
            '/model/pdu/0/outlet/0', 'setPowerState', {'pstate': 1}
        )

    def test_off_calls_setPowerState_with_pstate_0(self):
        self.client.set_outlet_power_state(0, 'off')
        self.client._rpc.assert_called_once_with(
            '/model/pdu/0/outlet/0', 'setPowerState', {'pstate': 0}
        )

    def test_cycle_calls_cyclePowerState(self):
        self.client.set_outlet_power_state(0, 'cycle')
        self.client._rpc.assert_called_once_with(
            '/model/pdu/0/outlet/0', 'cyclePowerState'
        )

    def test_invalid_state_raises(self):
        with self.assertRaises(PDUClientError) as ctx:
            self.client.set_outlet_power_state(0, 'restart')
        self.assertIn('Invalid power state', str(ctx.exception))

    def test_outlet_index_in_path(self):
        """Outlet index (0-based) is used in the RPC path."""
        self.client.set_outlet_power_state(5, 'on')
        path = self.client._rpc.call_args[0][0]
        self.assertEqual(path, '/model/pdu/0/outlet/5')


# ---------------------------------------------------------------------------
# set_outlet_name() tests
# ---------------------------------------------------------------------------

class TestSetOutletName(unittest.TestCase):

    def setUp(self):
        self.client = _make_client()

    def test_name_is_updated_in_settings(self):
        """Merges the new name into getSettings result and calls setSettings."""
        existing_settings = {'otherKey': 'value'}
        self.client._get_outlet_rids = MagicMock(return_value=['/tfwopaque/outlet/0'])
        self.client._rpc = MagicMock(side_effect=[existing_settings, None])

        self.client.set_outlet_name(0, 'Server-01')

        # Verify the second _rpc call (setSettings) contains the correct name
        second_call = self.client._rpc.call_args_list[1]
        sent_settings = second_call[1]['settings'] if 'settings' in second_call[1] else second_call[0][2]['settings']
        self.assertEqual(sent_settings['name'], 'Server-01')
        # Existing keys are preserved
        self.assertEqual(sent_settings['otherKey'], 'value')

    def test_out_of_range_raises(self):
        self.client._get_outlet_rids = MagicMock(return_value=['/tfwopaque/outlet/0'])
        with self.assertRaises(PDUClientError) as ctx:
            self.client.set_outlet_name(5, 'SomeName')
        self.assertIn('out of range', str(ctx.exception))


# ---------------------------------------------------------------------------
# set_inlet_name() tests
# ---------------------------------------------------------------------------

class TestSetInletName(unittest.TestCase):

    def setUp(self):
        self.client = _make_client()

    def test_name_is_updated_in_settings(self):
        existing_settings = {'label': 'Inlet I1'}
        self.client._get_inlet_rids = MagicMock(return_value=['/tfwopaque/inlet/0'])
        self.client._rpc = MagicMock(side_effect=[existing_settings, None])

        self.client.set_inlet_name(0, 'Main Input')

        second_call = self.client._rpc.call_args_list[1]
        sent_settings = second_call[1]['settings'] if 'settings' in second_call[1] else second_call[0][2]['settings']
        self.assertEqual(sent_settings['name'], 'Main Input')

    def test_out_of_range_raises(self):
        self.client._get_inlet_rids = MagicMock(return_value=[])
        with self.assertRaises(PDUClientError) as ctx:
            self.client.set_inlet_name(0, 'Name')
        self.assertIn('out of range', str(ctx.exception))


# ---------------------------------------------------------------------------
# get_all_outlet_data() tests
# ---------------------------------------------------------------------------

class TestGetAllOutletData(unittest.TestCase):

    def setUp(self):
        self.client = _make_client()

    def test_raises_when_no_rids(self):
        """Raises PDUClientError when no outlet RIDs are found."""
        self.client._get_outlet_rids = MagicMock(return_value=[])
        with self.assertRaises(PDUClientError):
            self.client.get_all_outlet_data()

    def test_returns_one_entry_per_rid(self):
        """Returns one entry per outlet RID."""
        rids = ['/tfwopaque/outlet/0', '/tfwopaque/outlet/1']
        self.client._get_outlet_rids = MagicMock(return_value=rids)
        self.client._build_outlet_entry = MagicMock(side_effect=[
            {'outlet_number': 1},
            {'outlet_number': 2},
        ])
        result = self.client.get_all_outlet_data()
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]['outlet_number'], 1)
        self.assertEqual(result[1]['outlet_number'], 2)


# ---------------------------------------------------------------------------
# get_single_outlet_data() tests
# ---------------------------------------------------------------------------

class TestGetSingleOutletData(unittest.TestCase):

    def setUp(self):
        self.client = _make_client()
        self.client._get_outlet_rids = MagicMock(return_value=[
            '/tfwopaque/outlet/0',
            '/tfwopaque/outlet/1',
        ])

    def test_returns_correct_outlet(self):
        self.client._build_outlet_entry = MagicMock(return_value={'outlet_number': 2})
        result = self.client.get_single_outlet_data(1)
        self.assertEqual(result['outlet_number'], 2)
        # Verify outlet_index=1 is passed to _build_outlet_entry
        self.client._build_outlet_entry.assert_called_once_with('/tfwopaque/outlet/1', 1)

    def test_out_of_range_raises(self):
        with self.assertRaises(PDUClientError) as ctx:
            self.client.get_single_outlet_data(5)
        self.assertIn('out of range', str(ctx.exception))


# ---------------------------------------------------------------------------
# _get_outlet_rids() / _get_inlet_rids() tests
# ---------------------------------------------------------------------------

class TestGetRids(unittest.TestCase):

    def setUp(self):
        self.client = _make_client()

    def test_outlet_rids_returns_rid_list(self):
        self.client._rpc = MagicMock(return_value=[
            {'rid': '/tfwopaque/outlet/0'},
            {'rid': '/tfwopaque/outlet/1'},
        ])
        result = self.client._get_outlet_rids()
        self.assertEqual(result, ['/tfwopaque/outlet/0', '/tfwopaque/outlet/1'])

    def test_outlet_rids_filters_non_dict_items(self):
        """Non-dict items are filtered out."""
        self.client._rpc = MagicMock(return_value=[
            {'rid': '/tfwopaque/outlet/0'},
            'not_a_dict',
            None,
        ])
        result = self.client._get_outlet_rids()
        self.assertEqual(result, ['/tfwopaque/outlet/0'])

    def test_outlet_rids_filters_items_without_rid(self):
        """Dicts without a 'rid' key are filtered out."""
        self.client._rpc = MagicMock(return_value=[
            {'rid': '/tfwopaque/outlet/0'},
            {'name': 'no_rid'},
        ])
        result = self.client._get_outlet_rids()
        self.assertEqual(result, ['/tfwopaque/outlet/0'])

    def test_outlet_rids_empty_on_none(self):
        """Returns empty list when _rpc returns None."""
        self.client._rpc = MagicMock(return_value=None)
        result = self.client._get_outlet_rids()
        self.assertEqual(result, [])

    def test_inlet_rids_returns_rid_list(self):
        self.client._rpc = MagicMock(return_value=[
            {'rid': '/tfwopaque/inlet/0'},
        ])
        result = self.client._get_inlet_rids()
        self.assertEqual(result, ['/tfwopaque/inlet/0'])

    def test_inlet_rids_filters_non_dict(self):
        self.client._rpc = MagicMock(return_value=[42, {'rid': '/tfwopaque/inlet/0'}])
        result = self.client._get_inlet_rids()
        self.assertEqual(result, ['/tfwopaque/inlet/0'])


# ---------------------------------------------------------------------------
# _get_sensor_value() tests
# ---------------------------------------------------------------------------

class TestGetSensorValue(unittest.TestCase):

    def setUp(self):
        self.client = _make_client()

    def test_returns_value_from_reading(self):
        self.client._rpc = MagicMock(return_value={'value': 120.5, 'timestamp': 1234567890})
        result = self.client._get_sensor_value('/tfwopaque/sensor/voltage')
        self.assertEqual(result, 120.5)

    def test_returns_none_for_non_dict_result(self):
        """Returns None when result is not a dict."""
        self.client._rpc = MagicMock(return_value='not_a_dict')
        result = self.client._get_sensor_value('/tfwopaque/sensor/x')
        self.assertIsNone(result)

    def test_returns_none_when_no_value_key(self):
        self.client._rpc = MagicMock(return_value={'timestamp': 123})
        result = self.client._get_sensor_value('/tfwopaque/sensor/x')
        self.assertIsNone(result)

    def test_returns_none_when_rpc_returns_none(self):
        self.client._rpc = MagicMock(return_value=None)
        result = self.client._get_sensor_value('/tfwopaque/sensor/x')
        self.assertIsNone(result)


# ---------------------------------------------------------------------------
# _fetch_energy() tests
# ---------------------------------------------------------------------------

class TestFetchEnergy(unittest.TestCase):

    def setUp(self):
        self.client = _make_client()

    def test_returns_none_when_no_active_energy(self):
        result = self.client._fetch_energy({})
        self.assertEqual(result, (None, None))

    def test_returns_none_when_active_energy_empty_string(self):
        result = self.client._fetch_energy({'activeEnergy': ''})
        self.assertEqual(result, (None, None))

    def test_string_rid(self):
        """Handles activeEnergy as a string RID."""
        self.client._rpc = MagicMock(side_effect=[
            {'value': 1234.5},  # getReading
            {'seconds': 1700000000},  # getLastResetTime
        ])
        energy, reset = self.client._fetch_energy({'activeEnergy': '/tfwopaque/sensor/energy'})
        self.assertEqual(energy, 1234.5)
        self.assertEqual(reset, 1700000000)

    def test_dict_rid(self):
        """Handles activeEnergy as a {rid: ...} dict."""
        self.client._rpc = MagicMock(side_effect=[
            {'value': 500.0},
            1600000000,  # int reset time
        ])
        energy, reset = self.client._fetch_energy({'activeEnergy': {'rid': '/tfwopaque/sensor/e'}})
        self.assertEqual(energy, 500.0)
        self.assertEqual(reset, 1600000000)

    def test_dict_rid_without_rid_key(self):
        """Returns (None, None) when activeEnergy dict has an empty rid."""
        result = self.client._fetch_energy({'activeEnergy': {'rid': ''}})
        self.assertEqual(result, (None, None))

    def test_reset_time_failure_returns_none_reset(self):
        """reset_epoch is None when getLastResetTime raises PDUClientError."""
        self.client._rpc = MagicMock(side_effect=[
            {'value': 100.0},  # getReading
            PDUClientError('not supported'),  # getLastResetTime
        ])
        energy, reset = self.client._fetch_energy({'activeEnergy': '/tfwopaque/sensor/e'})
        self.assertEqual(energy, 100.0)
        self.assertIsNone(reset)


# ---------------------------------------------------------------------------
# _build_outlet_entry() tests
# ---------------------------------------------------------------------------

class TestBuildOutletEntry(unittest.TestCase):

    def setUp(self):
        self.client = _make_client()

    def test_full_data(self):
        """All fields populated when all RPC calls succeed."""
        self.client._rpc = MagicMock(side_effect=[
            {'powerState': 1},                          # getState
            {'name': 'Server-01'},                      # getSettings
            {                                            # getSensors
                'current': '/sensor/current',
                'activePower': '/sensor/power',
                'voltage': '/sensor/voltage',
                'powerFactor': '/sensor/pf',
                'activeEnergy': '/sensor/energy',
            },
            {'value': 1.5},   # getReading (current)
            {'value': 300.0}, # getReading (power)
            {'value': 100.0}, # getReading (voltage)
            {'value': 0.98},  # getReading (pf)
            {'value': 5000.0}, # getReading (energy)
            1700000000,        # getLastResetTime
        ])

        entry = self.client._build_outlet_entry('/tfwopaque/outlet/0', 0)

        self.assertEqual(entry['outlet_number'], 1)
        self.assertEqual(entry['name'], 'Server-01')
        self.assertEqual(entry['switchingState'], 'on')
        self.assertEqual(entry['current_a'], 1.5)
        self.assertEqual(entry['power_w'], 300.0)
        self.assertEqual(entry['voltage_v'], 100.0)
        self.assertEqual(entry['power_factor'], 0.98)
        self.assertEqual(entry['energy_wh'], 5000.0)
        self.assertEqual(entry['energy_reset_epoch'], 1700000000)

    def test_getstate_failure_returns_unknown(self):
        """switchingState is 'unknown' when getState fails."""
        self.client._rpc = MagicMock(side_effect=[
            PDUClientError('connection failed'),  # getState
            {'name': 'Out1'},                      # getSettings
            {},                                    # getSensors (empty)
        ])
        entry = self.client._build_outlet_entry('/tfwopaque/outlet/0', 0)
        self.assertEqual(entry['switchingState'], 'unknown')
        self.assertEqual(entry['name'], 'Out1')

    def test_all_rpc_failures_return_defaults(self):
        """Safely returns default values when all RPC calls fail."""
        self.client._rpc = MagicMock(side_effect=PDUClientError('fail'))
        entry = self.client._build_outlet_entry('/tfwopaque/outlet/0', 2)
        self.assertEqual(entry['outlet_number'], 3)
        self.assertEqual(entry['switchingState'], 'unknown')
        self.assertEqual(entry['name'], '')
        self.assertIsNone(entry['current_a'])

    def test_sensor_rid_as_dict(self):
        """Handles sensor RID in dict format."""
        self.client._rpc = MagicMock(side_effect=[
            {'powerState': 0},          # getState
            {'name': 'Out1'},           # getSettings
            {'current': {'rid': '/sensor/c'}},  # getSensors
            {'value': 2.5},             # getReading
        ])
        entry = self.client._build_outlet_entry('/rid', 0)
        self.assertEqual(entry['current_a'], 2.5)

    def test_values_are_rounded(self):
        """Sensor values are rounded to 2 decimal places."""
        self.client._rpc = MagicMock(side_effect=[
            {'powerState': 1},
            {'name': ''},
            {'current': '/sensor/c'},
            {'value': 1.23456789},
        ])
        entry = self.client._build_outlet_entry('/rid', 0)
        self.assertEqual(entry['current_a'], 1.23)


# ---------------------------------------------------------------------------
# _build_inlet_entry() tests
# ---------------------------------------------------------------------------

class TestBuildInletEntry(unittest.TestCase):

    def setUp(self):
        self.client = _make_client()

    def test_full_data(self):
        self.client._rpc = MagicMock(side_effect=[
            {'label': 'Main Input'},  # getMetaData
            {                          # getSensors
                'current': '/sensor/c',
                'activePower': '/sensor/p',
                'apparentPower': '/sensor/ap',
                'voltage': '/sensor/v',
                'powerFactor': '/sensor/pf',
                'lineFrequency': '/sensor/f',
                'activeEnergy': '/sensor/e',
            },
            {'value': 10.0},   # current
            {'value': 2000.0}, # activePower
            {'value': 2200.0}, # apparentPower
            {'value': 200.0},  # voltage
            {'value': 0.91},   # powerFactor
            {'value': 50.0},   # lineFrequency
            {'value': 50000.0}, # energy
            1700000000,         # getLastResetTime
        ])
        entry = self.client._build_inlet_entry('/tfwopaque/inlet/0', 0)
        self.assertEqual(entry['inlet_number'], 1)
        self.assertEqual(entry['name'], 'Main Input')
        self.assertEqual(entry['current_a'], 10.0)
        self.assertEqual(entry['power_w'], 2000.0)
        self.assertEqual(entry['apparent_power_va'], 2200.0)
        self.assertEqual(entry['voltage_v'], 200.0)
        self.assertEqual(entry['power_factor'], 0.91)
        self.assertEqual(entry['frequency_hz'], 50.0)
        self.assertEqual(entry['energy_wh'], 50000.0)

    def test_metadata_failure_returns_empty_name(self):
        self.client._rpc = MagicMock(side_effect=[
            PDUClientError('fail'),  # getMetaData
            {},                       # getSensors (empty)
        ])
        entry = self.client._build_inlet_entry('/rid', 0)
        self.assertEqual(entry['name'], '')

    def test_frequency_prefers_first_sensor(self):
        """When both frequency and lineFrequency exist, the first match wins."""
        self.client._rpc = MagicMock(side_effect=[
            {'label': ''},
            {'frequency': '/sensor/f1', 'lineFrequency': '/sensor/f2'},
            {'value': 60.0},   # frequency
            # lineFrequency is skipped because frequency_hz is already set
        ])
        entry = self.client._build_inlet_entry('/rid', 0)
        self.assertEqual(entry['frequency_hz'], 60.0)


# ---------------------------------------------------------------------------
# get_pdu_info() tests
# ---------------------------------------------------------------------------

class TestGetPduInfo(unittest.TestCase):

    def setUp(self):
        self.client = _make_client()

    def test_basic_metadata(self):
        """Basic hardware metadata is parsed correctly."""
        self.client._rpc = MagicMock(side_effect=[
            {   # /model/pdu/0 getMetaData
                'nameplate': {
                    'model': 'PX3-5000',
                    'serialNumber': 'SN12345',
                    'rating': {
                        'voltage': '100-240V',
                        'current': '16A',
                        'frequency': '50/60Hz',
                        'power': '3.8kW',
                    },
                },
                'fwRevision': '4.3.13',
                'hwRevision': 'A1',
                'macAddress': 'AA:BB:CC:DD:EE:FF',
            },
            PDUClientError('net fail'),  # /net getInfo
            PDUClientError('dt fail'),   # /datetime getCfg
        ])
        info = self.client.get_pdu_info()
        self.assertEqual(info['model'], 'PX3-5000')
        self.assertEqual(info['serial_number'], 'SN12345')
        self.assertEqual(info['firmware_version'], '4.3.13')
        self.assertEqual(info['hw_revision'], 'A1')
        self.assertEqual(info['rated_voltage'], '100-240V')
        self.assertEqual(info['rated_current'], '16A')
        self.assertEqual(info['pdu_mac_address'], 'AA:BB:CC:DD:EE:FF')

    def test_network_interfaces_parsed(self):
        """Network interfaces, DNS, and gateway are parsed correctly."""
        self.client._rpc = MagicMock(side_effect=[
            {'nameplate': {}, 'fwRevision': '', 'hwRevision': ''},  # getMetaData
            {   # /net getInfo
                'ifMap': [
                    {
                        'key': 'eth0',
                        'value': {
                            'label': 'ETH0',
                            'macAddr': 'AA:BB:CC:DD:EE:FF',
                            'ipv4': {
                                'addrsCidr': [{'addr': '192.168.1.100'}],
                                'configMethod': 1,
                            },
                        },
                    },
                    {'key': 'lo', 'value': {'macAddr': ''}},  # No MAC -> excluded
                ],
                'ethMap': [
                    {
                        'key': 'eth0',
                        'value': {'linkMode': {'speed': 3, 'duplexMode': 2}},
                    },
                ],
                'common': {
                    'dns': {'serverAddrs': ['8.8.8.8', '8.8.4.4']},
                    'routing': {
                        'ipv4Routes': [
                            {
                                'destNetAddrCidr': {'addr': '0.0.0.0', 'prefixLen': 0},
                                'nextHopAddr': '192.168.1.1',
                            },
                        ],
                    },
                },
            },
            PDUClientError('dt fail'),  # /datetime getCfg
        ])
        info = self.client.get_pdu_info()
        self.assertEqual(len(info['network_interfaces']), 1)
        iface = info['network_interfaces'][0]
        self.assertEqual(iface['name'], 'ETH0')
        self.assertEqual(iface['mac_address'], 'AA:BB:CC:DD:EE:FF')
        self.assertEqual(iface['ip_address'], '192.168.1.100')
        self.assertEqual(iface['config_method'], 'DHCP')
        self.assertEqual(iface['link_speed'], '1G Full')
        self.assertEqual(info['dns_servers'], '8.8.8.8, 8.8.4.4')
        self.assertEqual(info['default_gateway'], '192.168.1.1')

    def test_datetime_and_ntp(self):
        """Device time and NTP servers are fetched correctly."""
        self.client._rpc = MagicMock(side_effect=[
            {'nameplate': {}},  # getMetaData
            PDUClientError('net fail'),  # /net getInfo
            {'cfg': {'deviceTime': 1700000000}},  # /datetime getCfg
            ['ntp1.example.com', 'ntp2.example.com'],  # getActiveNtpServers
        ])
        info = self.client.get_pdu_info()
        self.assertEqual(info['device_time_epoch'], 1700000000)
        self.assertEqual(info['ntp_servers'], 'ntp1.example.com, ntp2.example.com')

    def test_ntp_fallback_to_cfg(self):
        """Falls back to ntpCfg when getActiveNtpServers fails."""
        self.client._rpc = MagicMock(side_effect=[
            {'nameplate': {}},
            PDUClientError('net fail'),
            {'cfg': {
                'deviceTime': 1700000000,
                'ntpCfg': {'server1': 'ntp1.local', 'server2': 'ntp2.local'},
            }},
            PDUClientError('not supported'),  # getActiveNtpServers fails
        ])
        info = self.client.get_pdu_info()
        self.assertEqual(info['ntp_servers'], 'ntp1.local, ntp2.local')


# ---------------------------------------------------------------------------
# get_all_inlet_data() / get_single_inlet_data() tests
# ---------------------------------------------------------------------------

class TestGetAllInletData(unittest.TestCase):

    def setUp(self):
        self.client = _make_client()

    def test_returns_empty_when_no_rids(self):
        self.client._get_inlet_rids = MagicMock(return_value=[])
        result = self.client.get_all_inlet_data()
        self.assertEqual(result, [])

    def test_returns_entries_for_each_rid(self):
        self.client._get_inlet_rids = MagicMock(return_value=['/rid/0', '/rid/1'])
        self.client._build_inlet_entry = MagicMock(side_effect=[
            {'inlet_number': 1},
            {'inlet_number': 2},
        ])
        result = self.client.get_all_inlet_data()
        self.assertEqual(len(result), 2)


class TestGetSingleInletData(unittest.TestCase):

    def setUp(self):
        self.client = _make_client()
        self.client._get_inlet_rids = MagicMock(return_value=['/rid/0'])

    def test_returns_correct_inlet(self):
        self.client._build_inlet_entry = MagicMock(return_value={'inlet_number': 1})
        result = self.client.get_single_inlet_data(0)
        self.assertEqual(result['inlet_number'], 1)

    def test_out_of_range_raises(self):
        with self.assertRaises(PDUClientError) as ctx:
            self.client.get_single_inlet_data(5)
        self.assertIn('out of range', str(ctx.exception))


# ---------------------------------------------------------------------------
# get_outlet_power_state_by_index() — additional edge cases
# ---------------------------------------------------------------------------

class TestGetOutletPowerStateEdgeCases(unittest.TestCase):

    def setUp(self):
        self.client = _make_client()

    def test_dict_without_power_state_key(self):
        """Returns 'unknown' when result dict has no powerState key."""
        self.client._rpc = MagicMock(return_value={'otherKey': 'value'})
        result = self.client.get_outlet_power_state_by_index(0)
        self.assertEqual(result, 'unknown')

    def test_non_dict_result_uses_raw(self):
        """Uses raw value when result is not a dict."""
        self.client._rpc = MagicMock(return_value=1)
        result = self.client.get_outlet_power_state_by_index(0)
        self.assertEqual(result, 'on')


if __name__ == '__main__':
    unittest.main()
