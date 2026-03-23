import django_tables2 as tables
from netbox.tables import ChoiceFieldColumn, NetBoxTable, columns

from .models import ManagedPDU, PDUInlet, PDUOutlet


def _fmt2(value):
    """Format to 2 decimal places. Returns an em-dash for None."""
    if value is None:
        return "—"
    return f"{value:.2f}"


class ManagedPDUTable(NetBoxTable):
    name = tables.Column(
        accessor="device.name",
        linkify=lambda record: record.get_absolute_url(),
        verbose_name="Managed PDU",
    )
    device = tables.Column(linkify=True)
    api_url = tables.Column(verbose_name="API URL")
    sync_status = ChoiceFieldColumn(verbose_name="Sync Status")
    last_synced = tables.DateTimeColumn(verbose_name="Last Synced")
    outlet_count = tables.Column(verbose_name="Outlets")
    pdu_model = tables.Column(verbose_name="Model")
    serial_number = tables.Column(verbose_name="Serial")
    firmware_version = tables.Column(verbose_name="Firmware")

    class Meta(NetBoxTable.Meta):
        model = ManagedPDU
        fields = (
            "pk",
            "id",
            "name",
            "device",
            "api_url",
            "pdu_model",
            "serial_number",
            "firmware_version",
            "sync_status",
            "last_synced",
            "outlet_count",
            "actions",
        )
        default_columns = (
            "name",
            "device",
            "pdu_model",
            "serial_number",
            "firmware_version",
            "outlet_count",
            "sync_status",
            "last_synced",
            "actions",
        )


OUTLET_SYNC_BUTTON = """
{% if perms.netbox_pdu_plugin.change_managedpdu %}
<form method="post" action="{% url 'plugins:netbox_pdu_plugin:pduoutlet_power_on' pk=record.pk %}" style="display:inline">
  {% csrf_token %}
  <button type="submit" class="btn btn-sm btn-success" title="Power ON">
    <i class="mdi mdi-power"></i>
  </button>
</form>
<form method="post" action="{% url 'plugins:netbox_pdu_plugin:pduoutlet_power_off' pk=record.pk %}" style="display:inline">
  {% csrf_token %}
  <button type="submit" class="btn btn-sm btn-danger" title="Power OFF">
    <i class="mdi mdi-power-off"></i>
  </button>
</form>
<form method="post" action="{% url 'plugins:netbox_pdu_plugin:pduoutlet_power_cycle' pk=record.pk %}" style="display:inline">
  {% csrf_token %}
  <button type="submit" class="btn btn-sm btn-warning" title="Power Cycle">
    <i class="mdi mdi-restart"></i>
  </button>
</form>
<form method="post" action="{% url 'plugins:netbox_pdu_plugin:pduoutlet_sync' pk=record.pk %}" style="display:inline">
  {% csrf_token %}
  <button type="submit" class="btn btn-sm btn-outline-primary" title="Sync this outlet">
    <i class="mdi mdi-refresh"></i>
  </button>
</form>
<form method="post" action="{% url 'plugins:netbox_pdu_plugin:pduoutlet_push_name' pk=record.pk %}" style="display:inline">
  {% csrf_token %}
  <button type="submit" class="btn btn-sm btn-outline-secondary" title="Push name to PDU">
    <i class="mdi mdi-upload"></i>
  </button>
</form>
{% endif %}
"""

INLET_SYNC_BUTTON = """
{% if perms.netbox_pdu_plugin.change_managedpdu %}
<form method="post" action="{% url 'plugins:netbox_pdu_plugin:pduinlet_sync' pk=record.pk %}" style="display:inline">
  {% csrf_token %}
  <button type="submit" class="btn btn-sm btn-outline-primary" title="Sync this inlet">
    <i class="mdi mdi-refresh"></i>
  </button>
</form>
<form method="post" action="{% url 'plugins:netbox_pdu_plugin:pduinlet_push_name' pk=record.pk %}" style="display:inline">
  {% csrf_token %}
  <button type="submit" class="btn btn-sm btn-outline-secondary" title="Push name to PDU">
    <i class="mdi mdi-upload"></i>
  </button>
</form>
{% endif %}
"""


class PDUOutletTable(NetBoxTable):
    pk = columns.ToggleColumn()
    actions = columns.ActionsColumn(actions=("edit",), extra_buttons=OUTLET_SYNC_BUTTON)
    outlet_number = tables.Column(linkify=True, verbose_name="Outlet")
    outlet_name = tables.Column(verbose_name="Name")
    managed_pdu = tables.Column(linkify=True, verbose_name="PDU")
    connected_device = tables.Column(linkify=True, verbose_name="Connected Device")
    status = ChoiceFieldColumn()
    current_a = tables.Column(verbose_name="Current (A)")
    power_w = tables.Column(verbose_name="Power (W)")
    apparent_power_va = tables.Column(verbose_name="Apparent Power (VA)")
    voltage_v = tables.Column(verbose_name="Voltage (V)")
    power_factor = tables.Column(verbose_name="Power Factor")
    last_updated_from_pdu = tables.DateTimeColumn(verbose_name="Last Updated")

    def render_outlet_number(self, value):
        return f"Outlet {value}"

    def render_current_a(self, value):
        return _fmt2(value)

    def render_power_w(self, value):
        return _fmt2(value)

    def render_apparent_power_va(self, value):
        return _fmt2(value)

    def render_voltage_v(self, value):
        return _fmt2(value)

    def render_power_factor(self, value):
        return _fmt2(value)

    class Meta(NetBoxTable.Meta):
        model = PDUOutlet
        fields = (
            "pk",
            "id",
            "outlet_number",
            "outlet_name",
            "managed_pdu",
            "connected_device",
            "status",
            "current_a",
            "power_w",
            "apparent_power_va",
            "voltage_v",
            "power_factor",
            "last_updated_from_pdu",
            "actions",
        )
        default_columns = (
            "pk",
            "managed_pdu",
            "outlet_number",
            "outlet_name",
            "connected_device",
            "status",
            "current_a",
            "power_w",
            "apparent_power_va",
            "voltage_v",
            "power_factor",
            "last_updated_from_pdu",
            "actions",
        )


class PDUInletTable(NetBoxTable):
    actions = columns.ActionsColumn(actions=("edit",), extra_buttons=INLET_SYNC_BUTTON)
    inlet_number = tables.Column(linkify=True, verbose_name="Inlet")
    inlet_name = tables.Column(verbose_name="Name")
    managed_pdu = tables.Column(linkify=True, verbose_name="PDU")
    current_a = tables.Column(verbose_name="Current (A)")
    power_w = tables.Column(verbose_name="Active Power (W)")
    apparent_power_va = tables.Column(verbose_name="Apparent Power (VA)")
    voltage_v = tables.Column(verbose_name="Voltage (V)")
    power_factor = tables.Column(verbose_name="Power Factor")
    frequency_hz = tables.Column(verbose_name="Frequency (Hz)")
    last_updated_from_pdu = tables.DateTimeColumn(verbose_name="Last Updated")

    def render_inlet_number(self, value):
        return f"Inlet {value}"

    def render_current_a(self, value):
        return _fmt2(value)

    def render_power_w(self, value):
        return _fmt2(value)

    def render_apparent_power_va(self, value):
        return _fmt2(value)

    def render_voltage_v(self, value):
        return _fmt2(value)

    def render_power_factor(self, value):
        return _fmt2(value)

    def render_frequency_hz(self, value):
        return _fmt2(value)

    class Meta(NetBoxTable.Meta):
        model = PDUInlet
        fields = (
            "pk",
            "id",
            "inlet_number",
            "inlet_name",
            "managed_pdu",
            "current_a",
            "power_w",
            "apparent_power_va",
            "voltage_v",
            "power_factor",
            "frequency_hz",
            "last_updated_from_pdu",
            "actions",
        )
        default_columns = (
            "managed_pdu",
            "inlet_number",
            "inlet_name",
            "current_a",
            "power_w",
            "apparent_power_va",
            "voltage_v",
            "power_factor",
            "frequency_hz",
            "last_updated_from_pdu",
            "actions",
        )
