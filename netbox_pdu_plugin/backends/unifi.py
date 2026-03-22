"""
Ubiquiti UniFi SmartPower PDU (USP-PDU-Pro) backend.

API: UniFi Network Controller REST API (JSON)
Authentication: Session cookie (POST /api/auth/login for UDM, /api/login for standalone)

api_url examples:
  https://192.168.1.1          (UDM/UCG — controller is the gateway itself)
  https://unifi.local:8443     (standalone UniFi Network controller)

The backend auto-detects UDM vs standalone by trying both login endpoints.
Site defaults to "default". To use a different site, append /s/<site> to api_url.
"""
import logging
import re
import time

import requests

from .base import BasePDUClient, PDUClientError

logger = logging.getLogger(__name__)


class UniFiPDUClient(BasePDUClient):
    """Ubiquiti UniFi PDU client via UniFi Network Controller API."""

    # (login path, api prefix template) — tried in order
    _AUTH_PATHS = [
        ('/api/auth/login', '/proxy/network/api/s/{site}/'),  # UDM / UCG style
        ('/api/login',      '/api/s/{site}/'),                # Standalone controller
    ]

    def __init__(self, base_url: str, username: str, password: str,
                 verify_ssl: bool = True, managed_pdu=None, **kwargs):
        super().__init__(base_url, username, password, verify_ssl)
        self.managed_pdu = managed_pdu
        self.session = requests.Session()
        if not verify_ssl:
            self.session.verify = False
            requests.packages.urllib3.disable_warnings()

        # Parse site from URL path (e.g. https://host/s/mysite → "mysite")
        m = re.search(r'/s/([^/]+)', base_url)
        self._site = m.group(1) if m else 'default'
        self._base = re.sub(r'/s/[^/]+.*', '', base_url).rstrip('/')

        self._api_prefix = None   # set after successful login
        self._device_cache = None

    # ------------------------------------------------------------------
    # Auth & HTTP helpers
    # ------------------------------------------------------------------

    @property
    def _use_api_key(self) -> bool:
        """True if API key mode (username empty, password = API key)."""
        return not self.username and bool(self.password)

    def _login(self) -> None:
        if self._api_prefix is not None:
            return

        if self._use_api_key:
            # API key auth — set header, detect UDM vs standalone by trying both prefixes
            self.session.headers['X-API-KEY'] = self.password
            for _, api_tpl in self._AUTH_PATHS:
                prefix = self._base + api_tpl.format(site=self._site)
                try:
                    resp = self.session.get(
                        prefix + 'stat/health',
                        verify=self.verify_ssl,
                        timeout=10,
                    )
                    if resp.status_code == 200:
                        self._api_prefix = prefix
                        logger.debug('UniFi API key auth OK (site=%s)', self._site)
                        return
                except requests.exceptions.RequestException:
                    continue
            # If health check fails, just use first prefix (UDM default)
            self._api_prefix = self._base + self._AUTH_PATHS[0][1].format(site=self._site)
            logger.debug('UniFi API key — using default UDM prefix (site=%s)', self._site)
            return

        # Username/password session auth
        for login_path, api_tpl in self._AUTH_PATHS:
            url = self._base + login_path
            try:
                resp = self.session.post(
                    url,
                    json={'username': self.username, 'password': self.password},
                    verify=self.verify_ssl,
                    timeout=10,
                )
                if resp.status_code in (200, 204):
                    self._api_prefix = self._base + api_tpl.format(site=self._site)
                    logger.debug('UniFi session login OK via %s (site=%s)', login_path, self._site)
                    return
            except requests.exceptions.RequestException:
                continue

        raise PDUClientError(
            'Failed to authenticate with UniFi controller. '
            'Check api_url, username, and password.'
        )

    def _get(self, path: str) -> list | dict:
        self._login()
        url = self._api_prefix + path
        try:
            resp = self.session.get(url, verify=self.verify_ssl, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            return data.get('data', data)
        except requests.exceptions.SSLError as e:
            raise PDUClientError(f'SSL error: {e}') from e
        except requests.exceptions.ConnectionError as e:
            raise PDUClientError(f'Connection error: {e}') from e
        except requests.exceptions.Timeout as e:
            raise PDUClientError(f'Request timed out: {url}') from e
        except requests.exceptions.HTTPError as e:
            raise PDUClientError(f'HTTP error {resp.status_code}: {e}') from e
        except ValueError as e:
            raise PDUClientError(f'JSON parse error: {e}') from e

    def _put(self, path: str, payload: dict) -> dict:
        self._login()
        url = self._api_prefix + path
        try:
            resp = self.session.put(url, json=payload, verify=self.verify_ssl, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            return data.get('data', data)
        except requests.exceptions.SSLError as e:
            raise PDUClientError(f'SSL error: {e}') from e
        except requests.exceptions.ConnectionError as e:
            raise PDUClientError(f'Connection error: {e}') from e
        except requests.exceptions.Timeout as e:
            raise PDUClientError(f'Request timed out: {url}') from e
        except requests.exceptions.HTTPError as e:
            raise PDUClientError(f'HTTP error {resp.status_code}: {e}') from e
        except ValueError as e:
            raise PDUClientError(f'JSON parse error: {e}') from e

    # ------------------------------------------------------------------
    # Device discovery
    # ------------------------------------------------------------------

    def _get_device(self) -> dict:
        """Return the PDU device dict, discovering it if necessary."""
        if self._device_cache is not None:
            return self._device_cache

        devices = self._get('stat/device')
        pdu_devices = [d for d in devices if d.get('outlet_table')]

        if not pdu_devices:
            raise PDUClientError('No PDU device with outlet_table found in UniFi site.')

        # Match by MAC address stored in ManagedPDU, then by device name, else first found
        if self.managed_pdu:
            stored_mac = getattr(self.managed_pdu, 'pdu_mac_address', '') or ''
            if stored_mac:
                norm = stored_mac.replace(':', '').replace('-', '').lower()
                for d in pdu_devices:
                    if d.get('mac', '').replace(':', '').lower() == norm:
                        self._device_cache = d
                        return d

            nb_name = self.managed_pdu.device.name if self.managed_pdu.device else None
            if nb_name:
                for d in pdu_devices:
                    if d.get('name', '') == nb_name:
                        self._device_cache = d
                        return d

        self._device_cache = pdu_devices[0]
        return self._device_cache

    def _invalidate_cache(self) -> None:
        self._device_cache = None

    def _get_outlet_overrides(self) -> list[dict]:
        """
        Build a complete outlet_overrides list from current device state.
        Must include ALL outlets to avoid unintended resets.
        """
        device = self._get_device()
        existing = {o['index']: o for o in device.get('outlet_overrides', [])}
        result = []
        for outlet in device.get('outlet_table', []):
            idx = outlet['index']
            ov = existing.get(idx, {})
            result.append({
                'index': idx,
                'name': ov.get('name', outlet.get('name', f'Outlet {idx}')),
                'relay_state': ov.get('relay_state', outlet.get('relay_state', True)),
                'cycle_enabled': ov.get('cycle_enabled', outlet.get('cycle_enabled', False)),
            })
        return result

    # ------------------------------------------------------------------
    # BasePDUClient interface
    # ------------------------------------------------------------------

    def get_pdu_info(self) -> dict:
        device = self._get_device()
        mac = device.get('mac', '')
        ip = device.get('ip', '')
        interfaces = []
        if mac:
            interfaces.append({
                'name': 'ETH0',
                'mac_address': mac,
                'ip_address': ip,
                'config_method': '',
                'link_speed': '',
            })
        budget = device.get('outlet_ac_power_budget', '')
        return {
            'model': device.get('model', ''),
            'serial_number': device.get('serial', ''),
            'firmware_version': device.get('version', ''),
            'hw_revision': '',
            'pdu_mac_address': mac,
            'rated_voltage': '',
            'rated_current': '',
            'rated_frequency': '',
            'rated_power': f'{budget} W' if budget else '',
            'dns_servers': '',
            'default_gateway': '',
            'device_time_epoch': None,
            'ntp_servers': '',
            'network_interfaces': interfaces,
        }

    def get_all_outlet_data(self) -> list[dict]:
        device = self._get_device()
        outlets = device.get('outlet_table', [])
        if not outlets:
            raise PDUClientError('No outlets found in UniFi PDU device data.')
        return [self._parse_outlet(o) for o in outlets]

    def get_single_outlet_data(self, outlet_index: int) -> dict:
        all_outlets = self.get_all_outlet_data()
        if outlet_index >= len(all_outlets):
            raise PDUClientError(
                f'Outlet index {outlet_index} out of range (total: {len(all_outlets)})'
            )
        return all_outlets[outlet_index]

    @staticmethod
    def _parse_outlet(o: dict) -> dict:
        def _f(v):
            try:
                return round(float(v), 2)
            except (TypeError, ValueError):
                return None

        return {
            'outlet_number': o['index'],
            'name': o.get('name', ''),
            'switchingState': 'on' if o.get('relay_state') else 'off',
            'current_a': _f(o.get('outlet_current')),
            'power_w': _f(o.get('outlet_power')),
            'voltage_v': _f(o.get('outlet_voltage')),
            'power_factor': _f(o.get('outlet_power_factor')),
            'energy_wh': None,
            'energy_reset_epoch': None,
        }

    def get_all_inlet_data(self) -> list[dict]:
        device = self._get_device()
        try:
            total_power = round(float(device.get('outlet_ac_power_consumption', 0) or 0), 2)
        except (TypeError, ValueError):
            total_power = None
        return [{
            'inlet_number': 1,
            'name': 'Main Input',
            'current_a': None,
            'power_w': total_power,
            'apparent_power_va': None,
            'voltage_v': None,
            'power_factor': None,
            'frequency_hz': None,
            'energy_wh': None,
            'energy_reset_epoch': None,
        }]

    def get_single_inlet_data(self, inlet_index: int) -> dict:
        inlets = self.get_all_inlet_data()
        if inlet_index >= len(inlets):
            raise PDUClientError(
                f'Inlet index {inlet_index} out of range (total: {len(inlets)})'
            )
        return inlets[inlet_index]

    def set_outlet_power_state(self, outlet_index: int, state: str) -> None:
        device = self._get_device()
        device_id = device['_id']
        overrides = self._get_outlet_overrides()
        target_index = outlet_index + 1  # UniFi uses 1-based index

        if state == 'cycle':
            for o in overrides:
                if o['index'] == target_index:
                    o['relay_state'] = False
            self._put(f'rest/device/{device_id}', {'outlet_overrides': overrides})
            time.sleep(3)
            for o in overrides:
                if o['index'] == target_index:
                    o['relay_state'] = True
            self._put(f'rest/device/{device_id}', {'outlet_overrides': overrides})
        elif state in ('on', 'off'):
            for o in overrides:
                if o['index'] == target_index:
                    o['relay_state'] = (state == 'on')
            self._put(f'rest/device/{device_id}', {'outlet_overrides': overrides})
        else:
            raise PDUClientError(f'Invalid power state: {state!r}. Must be: on, off, cycle')

        self._invalidate_cache()
        logger.info('Set outlet %d power state to %s', target_index, state)

    def get_outlet_power_state_by_index(self, outlet_index: int) -> str:
        self._invalidate_cache()
        device = self._get_device()
        target_index = outlet_index + 1
        for o in device.get('outlet_table', []):
            if o['index'] == target_index:
                return 'on' if o.get('relay_state') else 'off'
        return 'unknown'

    def set_outlet_name(self, outlet_index: int, name: str) -> None:
        device = self._get_device()
        device_id = device['_id']
        overrides = self._get_outlet_overrides()
        target_index = outlet_index + 1
        for o in overrides:
            if o['index'] == target_index:
                o['name'] = name
        self._put(f'rest/device/{device_id}', {'outlet_overrides': overrides})
        self._invalidate_cache()
        logger.info('Set outlet %d name to %r', target_index, name)

    def set_inlet_name(self, inlet_index: int, name: str) -> None:
        raise PDUClientError('Inlet name setting is not supported for UniFi PDU.')
