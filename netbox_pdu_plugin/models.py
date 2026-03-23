from dcim.models import Device
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from netbox.models import NetBoxModel

from .choices import LinePairChoices, OutletStatusChoices, SyncStatusChoices, VendorChoices


class ManagedPDU(NetBoxModel):
    """
    Configuration for a managed PDU. Linked to a Device registered in NetBox,
    and holds the connection details for the PDU management API.
    """

    device = models.OneToOneField(
        to=Device,
        on_delete=models.CASCADE,
        related_name="managed_pdu",
        verbose_name=_("Device"),
        help_text=_("PDU device registered in NetBox"),
    )
    vendor = models.CharField(
        max_length=30,
        choices=VendorChoices,
        default=VendorChoices.RARITAN,
        verbose_name=_("Vendor"),
        help_text=_("PDU vendor / communication protocol"),
    )
    api_url = models.CharField(
        max_length=200,
        verbose_name=_("API URL"),
        help_text=_("Base URL of the PDU or controller (e.g. https://192.168.1.100)"),
    )
    api_username = models.CharField(
        max_length=100,
        blank=True,
        verbose_name=_("API Username"),
    )
    api_password = models.CharField(
        max_length=200,
        verbose_name=_("API Password"),
    )
    verify_ssl = models.BooleanField(
        default=False,
        verbose_name=_("Verify SSL"),
        help_text=_("Verify the SSL certificate when connecting via HTTPS"),
    )
    last_synced = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Last Synced"),
    )
    last_metrics_fetched = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Last Metrics Fetched"),
    )
    sync_status = models.CharField(
        max_length=30,
        choices=SyncStatusChoices,
        default=SyncStatusChoices.NEVER,
        verbose_name=_("Sync Status"),
    )
    pdu_model = models.CharField(
        max_length=100,
        blank=True,
        verbose_name=_("PDU Model"),
    )
    serial_number = models.CharField(
        max_length=100,
        blank=True,
        verbose_name=_("Serial Number"),
    )
    firmware_version = models.CharField(
        max_length=100,
        blank=True,
        verbose_name=_("Firmware Version"),
    )
    rated_voltage = models.CharField(
        max_length=20,
        blank=True,
        verbose_name=_("Rated Voltage"),
    )
    rated_current = models.CharField(
        max_length=20,
        blank=True,
        verbose_name=_("Rated Current"),
    )
    rated_frequency = models.CharField(
        max_length=20,
        blank=True,
        verbose_name=_("Rated Frequency"),
    )
    rated_power = models.CharField(
        max_length=20,
        blank=True,
        verbose_name=_("Rated Power"),
    )
    hw_revision = models.CharField(
        max_length=50,
        blank=True,
        verbose_name=_("HW Revision"),
    )
    pdu_mac_address = models.CharField(
        max_length=17,
        blank=True,
        verbose_name=_("PDU MAC Address"),
    )
    default_gateway = models.CharField(
        max_length=50,
        blank=True,
        verbose_name=_("Default Gateway"),
    )
    dns_servers = models.CharField(
        max_length=200,
        blank=True,
        verbose_name=_("DNS Servers"),
        help_text=_("Comma-separated list of DNS server addresses"),
    )
    device_time = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Device Time"),
        help_text=_("Current time reported by the PDU at last sync"),
    )
    ntp_servers = models.CharField(
        max_length=200,
        blank=True,
        verbose_name=_("NTP Servers"),
        help_text=_("Comma-separated list of NTP server addresses"),
    )
    comments = models.TextField(
        blank=True,
    )

    class Meta:
        ordering = ("device",)
        verbose_name = _("Managed PDU")
        verbose_name_plural = _("Managed PDUs")

    def __str__(self):
        return f"{self.device} (PDU)"

    def get_absolute_url(self):
        return reverse("plugins:netbox_pdu_plugin:managedpdu", args=[self.pk])

    def get_sync_status_color(self):
        return SyncStatusChoices.colors.get(self.sync_status)

    @property
    def phase_type(self):
        """Returns 'three' if 3-phase data exists, 'single' if inlets exist but no 3-phase data, None if unknown."""
        if self.inlet_linepairs.exists():
            return "three"
        if self.inlets.filter(poleline_l1_current_a__isnull=False).exists():
            return "three"
        if self.inlets.exists():
            return "single"
        return None


class PDUOutlet(NetBoxModel):
    """
    Status and power data for each outlet of a PDU.
    Stores values retrieved from the PDU API during synchronization.
    """

    managed_pdu = models.ForeignKey(
        to=ManagedPDU,
        on_delete=models.CASCADE,
        related_name="outlets",
        verbose_name=_("Managed PDU"),
    )
    outlet_number = models.PositiveIntegerField(
        verbose_name=_("Outlet Number"),
        help_text=_("Outlet number on the PDU"),
    )
    outlet_name = models.CharField(
        max_length=100,
        blank=True,
        verbose_name=_("Outlet Name"),
        help_text=_("Outlet name retrieved from the PDU"),
    )
    connected_device = models.ForeignKey(
        to=Device,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pdu_outlets",
        verbose_name=_("Connected Device"),
        help_text=_("Device connected to this outlet (manually configured)"),
    )
    status = models.CharField(
        max_length=30,
        choices=OutletStatusChoices,
        default=OutletStatusChoices.UNKNOWN,
        verbose_name=_("Status"),
    )
    current_a = models.FloatField(
        null=True,
        blank=True,
        verbose_name=_("Current (A)"),
        help_text=_("Current value (amperes)"),
    )
    power_w = models.FloatField(
        null=True,
        blank=True,
        verbose_name=_("Power (W)"),
        help_text=_("Active power (watts)"),
    )
    voltage_v = models.FloatField(
        null=True,
        blank=True,
        verbose_name=_("Voltage (V)"),
        help_text=_("Voltage (volts)"),
    )
    power_factor = models.FloatField(
        null=True,
        blank=True,
        verbose_name=_("Power Factor"),
        help_text=_("Power factor"),
    )
    energy_wh = models.FloatField(
        null=True,
        blank=True,
        verbose_name=_("Accumulated Energy (Wh)"),
        help_text=_("Accumulated active energy since last reset (watt-hours)"),
    )
    energy_reset_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Energy Reset At"),
        help_text=_("Timestamp when the energy accumulation was last reset"),
    )
    last_updated_from_pdu = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Last Updated from PDU"),
        help_text=_("Timestamp of the last data retrieval from the PDU"),
    )
    comments = models.TextField(
        blank=True,
        default="",
    )

    class Meta:
        ordering = ("managed_pdu", "outlet_number")
        unique_together = ("managed_pdu", "outlet_number")
        verbose_name = _("PDU Outlet")
        verbose_name_plural = _("PDU Outlets")

    def __str__(self):
        return f"{self.managed_pdu} - Outlet {self.outlet_number}"

    def get_absolute_url(self):
        return reverse("plugins:netbox_pdu_plugin:pduoutlet", args=[self.pk])

    def get_status_color(self):
        return OutletStatusChoices.colors.get(self.status)


class PDUInlet(NetBoxModel):
    """
    Power data for a PDU inlet (input side).
    Holds whole-PDU power consumption, current, voltage, and related metrics.
    """

    managed_pdu = models.ForeignKey(
        to=ManagedPDU,
        on_delete=models.CASCADE,
        related_name="inlets",
        verbose_name=_("Managed PDU"),
    )
    inlet_number = models.PositiveIntegerField(
        verbose_name=_("Inlet Number"),
        help_text=_("Inlet number on the PDU"),
    )
    inlet_name = models.CharField(
        max_length=100,
        blank=True,
        verbose_name=_("Inlet Name"),
        help_text=_("Inlet name retrieved from the PDU"),
    )
    current_a = models.FloatField(
        null=True,
        blank=True,
        verbose_name=_("Current (A)"),
        help_text=_("Current value (amperes)"),
    )
    power_w = models.FloatField(
        null=True,
        blank=True,
        verbose_name=_("Active Power (W)"),
        help_text=_("Active power (watts)"),
    )
    apparent_power_va = models.FloatField(
        null=True,
        blank=True,
        verbose_name=_("Apparent Power (VA)"),
        help_text=_("Apparent power (volt-amperes)"),
    )
    voltage_v = models.FloatField(
        null=True,
        blank=True,
        verbose_name=_("Voltage (V)"),
        help_text=_("Voltage (volts)"),
    )
    power_factor = models.FloatField(
        null=True,
        blank=True,
        verbose_name=_("Power Factor"),
        help_text=_("Power factor"),
    )
    frequency_hz = models.FloatField(
        null=True,
        blank=True,
        verbose_name=_("Frequency (Hz)"),
        help_text=_("Frequency (hertz)"),
    )
    energy_wh = models.FloatField(
        null=True,
        blank=True,
        verbose_name=_("Accumulated Energy (Wh)"),
        help_text=_("Accumulated active energy since last reset (watt-hours)"),
    )
    energy_reset_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Energy Reset At"),
        help_text=_("Timestamp when the energy accumulation was last reset"),
    )
    # 3-phase: per-pole current readings (available via Prometheus only)
    poleline_l1_current_a = models.FloatField(
        null=True,
        blank=True,
        verbose_name=_("L1 Current (A)"),
        help_text=_("Per-phase current for L1 (3-phase PDUs only)"),
    )
    poleline_l2_current_a = models.FloatField(
        null=True,
        blank=True,
        verbose_name=_("L2 Current (A)"),
        help_text=_("Per-phase current for L2 (3-phase PDUs only)"),
    )
    poleline_l3_current_a = models.FloatField(
        null=True,
        blank=True,
        verbose_name=_("L3 Current (A)"),
        help_text=_("Per-phase current for L3 (3-phase PDUs only)"),
    )
    # 3-phase: current and voltage unbalance metrics
    unbalanced_current_pct = models.FloatField(
        null=True,
        blank=True,
        verbose_name=_("Current Unbalance (%)"),
        help_text=_("Phase current unbalance percentage (3-phase PDUs only)"),
    )
    unbalanced_ll_current_pct = models.FloatField(
        null=True,
        blank=True,
        verbose_name=_("L-L Current Unbalance (%)"),
        help_text=_("Line-to-line current unbalance percentage (3-phase PDUs only)"),
    )
    unbalanced_ll_voltage_pct = models.FloatField(
        null=True,
        blank=True,
        verbose_name=_("L-L Voltage Unbalance (%)"),
        help_text=_("Line-to-line voltage unbalance percentage (3-phase PDUs only)"),
    )
    last_updated_from_pdu = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Last Updated from PDU"),
        help_text=_("Timestamp of the last data retrieval from the PDU"),
    )
    comments = models.TextField(
        blank=True,
        default="",
    )

    class Meta:
        ordering = ("managed_pdu", "inlet_number")
        unique_together = ("managed_pdu", "inlet_number")
        verbose_name = _("PDU Inlet")
        verbose_name_plural = _("PDU Inlets")

    def __str__(self):
        return f"{self.managed_pdu} - Inlet {self.inlet_number}"

    def get_absolute_url(self):
        return reverse("plugins:netbox_pdu_plugin:pduinlet", args=[self.pk])


class PDUInletLinePair(models.Model):
    """
    Line-pair power data for a 3-phase PDU inlet.
    One row per inlet × line-pair combination (L1-L2, L2-L3, L3-L1).
    Replaced entirely on each PDU sync.
    """

    managed_pdu = models.ForeignKey(
        to=ManagedPDU,
        on_delete=models.CASCADE,
        related_name="inlet_linepairs",
        verbose_name=_("Managed PDU"),
    )
    inlet_number = models.PositiveIntegerField(
        default=1,
        verbose_name=_("Inlet Number"),
    )
    line_pair = models.CharField(
        max_length=4,
        choices=LinePairChoices,
        verbose_name=_("Line Pair"),
    )
    voltage_v = models.FloatField(
        null=True,
        blank=True,
        verbose_name=_("Voltage (V)"),
    )
    current_a = models.FloatField(
        null=True,
        blank=True,
        verbose_name=_("Current (A)"),
    )
    power_w = models.FloatField(
        null=True,
        blank=True,
        verbose_name=_("Active Power (W)"),
    )
    apparent_power_va = models.FloatField(
        null=True,
        blank=True,
        verbose_name=_("Apparent Power (VA)"),
    )
    power_factor = models.FloatField(
        null=True,
        blank=True,
        verbose_name=_("Power Factor"),
    )
    energy_wh = models.FloatField(
        null=True,
        blank=True,
        verbose_name=_("Accumulated Energy (Wh)"),
    )
    last_updated_from_pdu = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Last Updated from PDU"),
    )

    class Meta:
        ordering = ("managed_pdu", "inlet_number", "line_pair")
        unique_together = ("managed_pdu", "inlet_number", "line_pair")
        verbose_name = _("PDU Inlet Line Pair")
        verbose_name_plural = _("PDU Inlet Line Pairs")

    def __str__(self):
        return f"{self.managed_pdu} - Inlet {self.inlet_number} {self.line_pair}"


class PDUOverCurrentProtector(models.Model):
    """
    Over-current protector (circuit breaker) data for a PDU.
    One row per OCP (e.g. C1, C2, C3 on 3-phase PDUs).
    Updated in-place on each sync / metrics fetch.
    """

    managed_pdu = models.ForeignKey(
        to=ManagedPDU,
        on_delete=models.CASCADE,
        related_name="ocps",
        verbose_name=_("Managed PDU"),
    )
    ocp_id = models.CharField(
        max_length=10,
        verbose_name=_("OCP ID"),
        help_text=_("OCP identifier as reported by PDU (e.g. C1, C2, C3)"),
    )
    rating_current_a = models.FloatField(
        null=True,
        blank=True,
        verbose_name=_("Rating (A)"),
        help_text=_("Rated current capacity of the breaker"),
    )
    current_a = models.FloatField(
        null=True,
        blank=True,
        verbose_name=_("Current (A)"),
        help_text=_("Total measured current"),
    )
    poleline_l1_current_a = models.FloatField(
        null=True,
        blank=True,
        verbose_name=_("L1 Current (A)"),
    )
    poleline_l2_current_a = models.FloatField(
        null=True,
        blank=True,
        verbose_name=_("L2 Current (A)"),
    )
    poleline_l3_current_a = models.FloatField(
        null=True,
        blank=True,
        verbose_name=_("L3 Current (A)"),
    )
    tripped = models.BooleanField(
        null=True,
        blank=True,
        verbose_name=_("Tripped"),
        help_text=_("True if the breaker has tripped (circuit open)"),
    )
    last_updated_from_pdu = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Last Updated from PDU"),
    )

    class Meta:
        ordering = ("managed_pdu", "ocp_id")
        unique_together = ("managed_pdu", "ocp_id")
        verbose_name = _("PDU Over-Current Protector")
        verbose_name_plural = _("PDU Over-Current Protectors")

    def __str__(self):
        return f"{self.managed_pdu} - OCP {self.ocp_id}"


class PDUNetworkInterface(models.Model):
    """
    Network interface information for a managed PDU.
    Supports multiple NICs (e.g. ETH1, ETH2).
    Replaced entirely on each PDU sync.
    """

    managed_pdu = models.ForeignKey(
        to=ManagedPDU,
        on_delete=models.CASCADE,
        related_name="network_interfaces",
        verbose_name=_("Managed PDU"),
    )
    interface_name = models.CharField(
        max_length=50,
        verbose_name=_("Interface"),
        help_text=_("Network interface name (e.g. ETH1, ETH2)"),
    )
    mac_address = models.CharField(
        max_length=17,
        blank=True,
        verbose_name=_("MAC Address"),
    )
    ip_address = models.CharField(
        max_length=50,
        blank=True,
        verbose_name=_("IP Address"),
    )
    config_method = models.CharField(
        max_length=10,
        blank=True,
        verbose_name=_("Config Method"),
        help_text=_("DHCP or Static"),
    )
    link_speed = models.CharField(
        max_length=20,
        blank=True,
        verbose_name=_("Link Speed"),
    )

    class Meta:
        ordering = ("managed_pdu", "interface_name")
        unique_together = ("managed_pdu", "interface_name")
        verbose_name = _("PDU Network Interface")
        verbose_name_plural = _("PDU Network Interfaces")

    def __str__(self):
        return f"{self.managed_pdu} - {self.interface_name} ({self.mac_address})"
