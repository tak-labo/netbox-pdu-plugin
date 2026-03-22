"""
Base interface for PDU vendor backends.

To add a new vendor:
1. Create backends/<vendor>.py implementing BasePDUClient
2. Register it in backends/__init__._VENDOR_BACKENDS
3. Add the vendor to choices.VendorChoices
"""
from abc import ABC, abstractmethod


class PDUClientError(Exception):
    """Raised when communication with a PDU fails."""
    pass


class BasePDUClient(ABC):
    """
    Abstract base class for PDU vendor backends.

    All backends must implement these methods so that views and sync logic
    can work with any vendor without modification.
    """

    def __init__(self, base_url: str, username: str, password: str, verify_ssl: bool = True, **kwargs):
        self.base_url = base_url
        self.username = username
        self.password = password
        self.verify_ssl = verify_ssl

    @abstractmethod
    def get_pdu_info(self) -> dict:
        """
        Return basic PDU hardware information.

        Must contain:
            model            (str) - PDU model name
            serial_number    (str) - Serial number
            firmware_version (str) - Firmware version string
            network_interfaces (list[dict]) - each dict:
                name        (str) - interface name (e.g. 'ETH1')
                mac_address (str) - MAC address
                ip_address  (str) - IP address (may be empty)
        """

    @abstractmethod
    def get_all_outlet_data(self) -> list[dict]:
        """
        Return status and sensor data for all outlets.

        Each dict must contain:
            outlet_number (int)   - 1-indexed
            name          (str)   - outlet label (may be empty)
            switchingState(str)   - 'on', 'off', or 'unknown'
            current_a     (float|None)
            power_w       (float|None)
            voltage_v     (float|None)
            power_factor  (float|None)
            energy_wh     (float|None)
            energy_reset_epoch (float|None)
        """

    @abstractmethod
    def get_single_outlet_data(self, outlet_index: int) -> dict:
        """Return data for one outlet (0-indexed). Same dict format as get_all_outlet_data."""

    @abstractmethod
    def get_all_inlet_data(self) -> list[dict]:
        """
        Return power data for all inlets.

        Each dict must contain:
            inlet_number      (int)
            name              (str)
            current_a         (float|None)
            power_w           (float|None)
            apparent_power_va (float|None)
            voltage_v         (float|None)
            power_factor      (float|None)
            frequency_hz      (float|None)
            energy_wh         (float|None)
            energy_reset_epoch(float|None)
        """

    @abstractmethod
    def get_single_inlet_data(self, inlet_index: int) -> dict:
        """Return data for one inlet (0-indexed). Same dict format as get_all_inlet_data."""

    @abstractmethod
    def set_outlet_power_state(self, outlet_index: int, state: str) -> None:
        """
        Change the power state of an outlet.

        Args:
            outlet_index: 0-indexed outlet number
            state: 'on', 'off', or 'cycle'
        """

    @abstractmethod
    def get_outlet_power_state_by_index(self, outlet_index: int) -> str:
        """Return the current power state of an outlet: 'on', 'off', or 'unknown'."""

    @abstractmethod
    def set_outlet_name(self, outlet_index: int, name: str) -> None:
        """Push a display name to the PDU outlet (0-indexed)."""

    @abstractmethod
    def set_inlet_name(self, inlet_index: int, name: str) -> None:
        """Push a display name to the PDU inlet (0-indexed)."""
