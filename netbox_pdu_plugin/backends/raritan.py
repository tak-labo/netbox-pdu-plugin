"""
Raritan Xerus PDU JSON-RPC 2.0 backend.

API documentation: https://help.raritan.com/json-rpc/4.3.13/

Transport: JSON-RPC 2.0 over HTTPS POST
Authentication: HTTP Basic Authentication
Endpoint: https://<pdu-ip>/<resource-path>

Main resource paths:
  /model/pdu/0              - PDU unit itself
  /model/pdu/0/outlet/{N}   - Outlet by index (0-based) — used for setPowerState
  /tfwopaque/...            - Opaque RIDs returned by getOutlets/getInlets
"""
import logging

import requests
from requests.auth import HTTPBasicAuth

from .base import BasePDUClient, PDUClientError

logger = logging.getLogger(__name__)


class RaritanPDUClient(BasePDUClient):
    """Raritan Xerus PDU JSON-RPC 2.0 client."""

    def __init__(self, base_url: str, username: str, password: str, verify_ssl: bool = True, **kwargs):
        super().__init__(base_url, username, password, verify_ssl)
        self.base_url = base_url.rstrip('/')
        self.session = requests.Session()
        self.session.auth = HTTPBasicAuth(username, password)
        self.session.headers.update({
            'Content-Type': 'application/json',
            'Accept': 'application/json',
        })
        self._rpc_id = 0

    def _next_id(self) -> int:
        self._rpc_id += 1
        return self._rpc_id

    def _rpc(self, path: str, method: str, params: dict | None = None) -> dict | list | None:
        """
        Send a JSON-RPC 2.0 request.
        Returns the _ret_ value from the response (or result as-is).
        Raises PDUClientError on any failure.
        """
        url = f'{self.base_url}{path}'
        payload = {
            'jsonrpc': '2.0',
            'method': method,
            'params': params or {},
            'id': self._next_id(),
        }
        try:
            response = self.session.post(url, json=payload, verify=self.verify_ssl, timeout=10)
            response.raise_for_status()
            data = response.json()

            if 'error' in data:
                raise PDUClientError(
                    f'JSON-RPC error [{path}::{method}]: '
                    f'code={data["error"].get("code")}, message={data["error"].get("message")}'
                )
            result = data.get('result')
            if isinstance(result, dict) and '_ret_' in result:
                return result['_ret_']
            return result

        except requests.exceptions.SSLError as e:
            raise PDUClientError(f'SSL error: {e}') from e
        except requests.exceptions.ConnectionError as e:
            raise PDUClientError(f'Connection error: {e}') from e
        except requests.exceptions.Timeout as e:
            raise PDUClientError(f'Request timed out: {url}') from e
        except requests.exceptions.HTTPError as e:
            raise PDUClientError(f'HTTP error {response.status_code}: {e}') from e
        except ValueError as e:
            raise PDUClientError(f'JSON parse error: {e}') from e

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_outlet_rids(self) -> list[str]:
        outlets = self._rpc('/model/pdu/0', 'getOutlets') or []
        return [o['rid'] for o in outlets if isinstance(o, dict) and 'rid' in o]

    def _get_inlet_rids(self) -> list[str]:
        inlets = self._rpc('/model/pdu/0', 'getInlets') or []
        return [o['rid'] for o in inlets if isinstance(o, dict) and 'rid' in o]

    def _get_sensor_value(self, sensor_path: str) -> float | None:
        result = self._rpc(sensor_path, 'getReading') or {}
        return result.get('value') if isinstance(result, dict) else None

    def _fetch_energy(self, sensors: dict) -> tuple[float | None, float | None]:
        """Return (energy_wh, reset_epoch_seconds) from a sensors dict."""
        sensor_rid = sensors.get('activeEnergy')
        if not sensor_rid:
            return None, None
        if isinstance(sensor_rid, dict):
            sensor_rid = sensor_rid.get('rid', '')
        if not sensor_rid:
            return None, None

        reading = self._rpc(sensor_rid, 'getReading') or {}
        energy = reading.get('value') if isinstance(reading, dict) else None

        reset_epoch = None
        try:
            reset_result = self._rpc(sensor_rid, 'getLastResetTime')
            if isinstance(reset_result, int | float):
                reset_epoch = reset_result
            elif isinstance(reset_result, dict):
                reset_epoch = reset_result.get('seconds') or reset_result.get('value')
        except PDUClientError:
            pass

        return energy, reset_epoch

    def _power_state_str(self, raw) -> str:
        if raw == 1:
            return 'on'
        if raw == 0:
            return 'off'
        return 'unknown'

    def _build_outlet_entry(self, rid: str, outlet_index: int) -> dict:
        entry = {
            'outlet_number': outlet_index + 1,
            'name': '',
            'switchingState': 'unknown',
            'current_a': None,
            'power_w': None,
            'voltage_v': None,
            'power_factor': None,
            'energy_wh': None,
            'energy_reset_epoch': None,
        }

        try:
            result = self._rpc(rid, 'getState')
            state = result.get('powerState') if isinstance(result, dict) else result
            entry['switchingState'] = self._power_state_str(state)
        except PDUClientError as e:
            logger.warning('Failed to get power state for outlet %d: %s', outlet_index + 1, e)

        try:
            settings = self._rpc(rid, 'getSettings') or {}
            entry['name'] = settings.get('name', '') if isinstance(settings, dict) else ''
        except PDUClientError as e:
            logger.debug('Failed to get name for outlet %d: %s', outlet_index + 1, e)

        try:
            sensors = self._rpc(rid, 'getSensors') or {}
            for sensor_key, field_name in [
                ('current', 'current_a'),
                ('activePower', 'power_w'),
                ('voltage', 'voltage_v'),
                ('powerFactor', 'power_factor'),
            ]:
                if sensor_key in sensors:
                    sensor_rid = sensors[sensor_key]
                    if isinstance(sensor_rid, dict):
                        sensor_rid = sensor_rid.get('rid', '')
                    val = self._get_sensor_value(sensor_rid)
                    if val is not None:
                        entry[field_name] = round(val, 2)

            energy, reset_epoch = self._fetch_energy(sensors)
            if energy is not None:
                entry['energy_wh'] = round(energy, 2)
            entry['energy_reset_epoch'] = reset_epoch
        except PDUClientError as e:
            logger.warning('Failed to get sensor data for outlet %d: %s', outlet_index + 1, e)

        return entry

    def _build_inlet_entry(self, rid: str, inlet_index: int) -> dict:
        entry = {
            'inlet_number': inlet_index + 1,
            'name': '',
            'current_a': None,
            'power_w': None,
            'apparent_power_va': None,
            'voltage_v': None,
            'power_factor': None,
            'frequency_hz': None,
            'energy_wh': None,
            'energy_reset_epoch': None,
        }

        try:
            meta = self._rpc(rid, 'getMetaData') or {}
            entry['name'] = meta.get('label', '') if isinstance(meta, dict) else ''
        except PDUClientError as e:
            logger.debug('Failed to get name for inlet %d: %s', inlet_index + 1, e)

        try:
            sensors = self._rpc(rid, 'getSensors') or {}
            sensor_map = {
                'current': 'current_a',
                'activePower': 'power_w',
                'apparentPower': 'apparent_power_va',
                'voltage': 'voltage_v',
                'powerFactor': 'power_factor',
                'frequency': 'frequency_hz',
                'lineFrequency': 'frequency_hz',
            }
            for sensor_key, field_name in sensor_map.items():
                if sensor_key in sensors and entry[field_name] is None:
                    sensor_rid = sensors[sensor_key]
                    if isinstance(sensor_rid, dict):
                        sensor_rid = sensor_rid.get('rid', '')
                    val = self._get_sensor_value(sensor_rid)
                    if val is not None:
                        entry[field_name] = round(val, 2)

            energy, reset_epoch = self._fetch_energy(sensors)
            if energy is not None:
                entry['energy_wh'] = round(energy, 2)
            entry['energy_reset_epoch'] = reset_epoch
        except PDUClientError as e:
            logger.warning('Failed to get sensor data for inlet %d: %s', inlet_index + 1, e)

        return entry

    # ------------------------------------------------------------------
    # BasePDUClient interface
    # ------------------------------------------------------------------

    _IP_CONFIG_METHOD = {0: 'Static', 1: 'DHCP', 2: 'DHCP'}
    _LINK_SPEED = {1: '10M', 2: '100M', 3: '1G', 4: '10G'}
    _LINK_DUPLEX = {1: 'Half', 2: 'Full'}

    def get_pdu_info(self) -> dict:
        """
        Fetch PDU hardware info.

        - Model / serial / firmware: /model/pdu/0 getMetaData
        - Network interfaces: /net getInfo
          ifMap is returned as a list of {key, value} objects.
          Only interfaces that have a MAC address are included.
          IP addresses are taken from ipv4.addrsCidr (CIDR notation).
        """
        meta = self._rpc('/model/pdu/0', 'getMetaData') or {}
        nameplate = meta.get('nameplate', {}) if isinstance(meta, dict) else {}
        rating = nameplate.get('rating', {}) if isinstance(nameplate, dict) else {}

        # --- Network interfaces, DNS, Gateway ---
        interfaces = []
        dns_servers = ''
        default_gateway = ''
        try:
            net_info = self._rpc('/net', 'getInfo') or {}

            # Build link-speed lookup from ethMap {key, value} list
            eth_speed = {}
            for item in net_info.get('ethMap', []):
                key = item.get('key', '')
                lm = item.get('value', {}).get('linkMode', {})
                speed = self._LINK_SPEED.get(lm.get('speed', 0), '')
                duplex = self._LINK_DUPLEX.get(lm.get('duplexMode', 0), '')
                if speed:
                    eth_speed[key] = f'{speed} {duplex}'.strip()

            for item in net_info.get('ifMap', []):
                key = item.get('key', '')
                iface = item.get('value', {})
                mac = iface.get('macAddr', '')
                if not mac:
                    continue
                label = iface.get('label') or iface.get('name', '')
                ipv4_addrs = [
                    e.get('addr', '')
                    for e in (iface.get('ipv4') or {}).get('addrsCidr', [])
                    if e.get('addr')
                ]
                config_int = (iface.get('ipv4') or {}).get('configMethod', -1)
                interfaces.append({
                    'name': label,
                    'mac_address': mac,
                    'ip_address': ', '.join(ipv4_addrs),
                    'config_method': self._IP_CONFIG_METHOD.get(config_int, ''),
                    'link_speed': eth_speed.get(key, ''),
                })

            # DNS
            dns_addrs = net_info.get('common', {}).get('dns', {}).get('serverAddrs', [])
            dns_servers = ', '.join(dns_addrs)

            # Default gateway = ipv4 route with dest 0.0.0.0/0
            for route in net_info.get('common', {}).get('routing', {}).get('ipv4Routes', []):
                dest = route.get('destNetAddrCidr', {})
                if dest.get('addr') == '0.0.0.0' and dest.get('prefixLen') == 0:
                    default_gateway = route.get('nextHopAddr', '')
                    break
        except PDUClientError as e:
            logger.warning('Failed to fetch network info: %s', e)

        # --- Device time and NTP ---
        device_time_epoch = None
        ntp_servers = ''
        try:
            dt_cfg = self._rpc('/datetime', 'getCfg') or {}
            cfg = dt_cfg.get('cfg', {}) if isinstance(dt_cfg, dict) else {}
            device_time_epoch = cfg.get('deviceTime')
            try:
                active_ntp = self._rpc('/datetime', 'getActiveNtpServers') or []
                ntp_servers = ', '.join(active_ntp) if isinstance(active_ntp, list) else ''
            except PDUClientError:
                ntp = cfg.get('ntpCfg', {})
                ntp_list = [s for s in [ntp.get('server1', ''), ntp.get('server2', '')] if s]
                ntp_servers = ', '.join(ntp_list)
        except PDUClientError as e:
            logger.warning('Failed to fetch datetime config: %s', e)

        return {
            'model': nameplate.get('model', ''),
            'serial_number': nameplate.get('serialNumber', ''),
            'firmware_version': meta.get('fwRevision', ''),
            'rated_voltage': rating.get('voltage', ''),
            'rated_current': rating.get('current', ''),
            'rated_frequency': rating.get('frequency', ''),
            'rated_power': rating.get('power', ''),
            'hw_revision': meta.get('hwRevision', ''),
            'pdu_mac_address': meta.get('macAddress', ''),
            'dns_servers': dns_servers,
            'default_gateway': default_gateway,
            'device_time_epoch': device_time_epoch,
            'ntp_servers': ntp_servers,
            'network_interfaces': interfaces,
        }

    def get_all_outlet_data(self) -> list[dict]:
        rids = self._get_outlet_rids()
        if not rids:
            raise PDUClientError('No outlet RIDs found. Check the API URL and credentials.')
        return [self._build_outlet_entry(rid, i) for i, rid in enumerate(rids)]

    def get_single_outlet_data(self, outlet_index: int) -> dict:
        rids = self._get_outlet_rids()
        if outlet_index >= len(rids):
            raise PDUClientError(f'Outlet index {outlet_index} out of range (total: {len(rids)})')
        return self._build_outlet_entry(rids[outlet_index], outlet_index)

    def get_all_inlet_data(self) -> list[dict]:
        rids = self._get_inlet_rids()
        if not rids:
            logger.warning('No inlet RIDs found.')
            return []
        return [self._build_inlet_entry(rid, i) for i, rid in enumerate(rids)]

    def get_single_inlet_data(self, inlet_index: int) -> dict:
        rids = self._get_inlet_rids()
        if inlet_index >= len(rids):
            raise PDUClientError(f'Inlet index {inlet_index} out of range (total: {len(rids)})')
        return self._build_inlet_entry(rids[inlet_index], inlet_index)

    def set_outlet_power_state(self, outlet_index: int, state: str) -> None:
        path = f'/model/pdu/0/outlet/{outlet_index}'
        if state == 'cycle':
            self._rpc(path, 'cyclePowerState')
        elif state == 'on':
            self._rpc(path, 'setPowerState', {'pstate': 1})
        elif state == 'off':
            self._rpc(path, 'setPowerState', {'pstate': 0})
        else:
            raise PDUClientError(f'Invalid power state: {state!r}. Must be: on, off, cycle')
        logger.info('Set outlet %d power state to %s', outlet_index + 1, state)

    def get_outlet_power_state_by_index(self, outlet_index: int) -> str:
        result = self._rpc(f'/model/pdu/0/outlet/{outlet_index}', 'getState')
        if result is None:
            return 'unknown'
        state = result.get('powerState') if isinstance(result, dict) else result
        return self._power_state_str(state)

    def set_outlet_name(self, outlet_index: int, name: str) -> None:
        rids = self._get_outlet_rids()
        if outlet_index >= len(rids):
            raise PDUClientError(f'Outlet index {outlet_index} out of range (total: {len(rids)})')
        rid = rids[outlet_index]
        current = self._rpc(rid, 'getSettings') or {}
        current['name'] = name
        self._rpc(rid, 'setSettings', {'settings': current})
        logger.info('Set outlet %d name to %r', outlet_index + 1, name)

    def set_inlet_name(self, inlet_index: int, name: str) -> None:
        rids = self._get_inlet_rids()
        if inlet_index >= len(rids):
            raise PDUClientError(f'Inlet index {inlet_index} out of range (total: {len(rids)})')
        rid = rids[inlet_index]
        current = self._rpc(rid, 'getSettings') or {}
        current['name'] = name
        self._rpc(rid, 'setSettings', {'settings': current})
        logger.info('Set inlet %d name to %r', inlet_index + 1, name)

    # ------------------------------------------------------------------
    # Threshold retrieval (Raritan-specific, optional interface)
    # ------------------------------------------------------------------

    _THRESHOLD_SENSORS_OUTLET = [
        ('current',     'Current',      'A'),
        ('activePower', 'Active Power', 'W'),
        ('voltage',     'Voltage',      'V'),
        ('powerFactor', 'Power Factor', ''),
    ]

    _THRESHOLD_SENSORS_INLET = [
        ('current',       'Current',       'A'),
        ('voltage',       'Voltage',       'V'),
        ('activePower',   'Active Power',  'W'),
        ('apparentPower', 'Apparent Power', 'VA'),
    ]

    def _fetch_thresholds_for_rid(self, rid: str, sensor_keys: list[tuple]) -> list[dict]:
        """Fetch threshold data for one outlet/inlet RID."""
        thresholds = []
        try:
            sensors = self._rpc(rid, 'getSensors') or {}
        except PDUClientError:
            return []
        for sensor_key, label, unit in sensor_keys:
            if sensor_key not in sensors:
                continue
            sensor_rid = sensors[sensor_key]
            if isinstance(sensor_rid, dict):
                sensor_rid = sensor_rid.get('rid', '')
            try:
                t = self._rpc(sensor_rid, 'getThresholds') or {}
            except PDUClientError:
                continue
            if not any([
                t.get('upperCriticalActive'), t.get('upperWarningActive'),
                t.get('lowerWarningActive'), t.get('lowerCriticalActive'),
            ]):
                continue
            thresholds.append({
                'label': label,
                'unit': unit,
                'lower_critical': t['lowerCritical'] if t.get('lowerCriticalActive') else None,
                'lower_warning':  t['lowerWarning']  if t.get('lowerWarningActive')  else None,
                'upper_warning':  t['upperWarning']  if t.get('upperWarningActive')  else None,
                'upper_critical': t['upperCritical'] if t.get('upperCriticalActive') else None,
            })
        return thresholds

    def get_outlet_thresholds(self, outlet_index: int) -> list[dict]:
        rids = self._get_outlet_rids()
        if outlet_index >= len(rids):
            return []
        return self._fetch_thresholds_for_rid(rids[outlet_index], self._THRESHOLD_SENSORS_OUTLET)

    def get_inlet_thresholds(self, inlet_index: int) -> list[dict]:
        rids = self._get_inlet_rids()
        if inlet_index >= len(rids):
            return []
        return self._fetch_thresholds_for_rid(rids[inlet_index], self._THRESHOLD_SENSORS_INLET)
