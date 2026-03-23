import logging
import re
from datetime import UTC, datetime, timedelta

import django_rq
from dcim.models import PowerOutlet, PowerPort
from django.contrib import messages
from django.db import transaction
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views import View
from netbox.views import generic
from utilities.views import register_model_view

from . import filtersets, forms, jobs, models, tables
from .jobs import fetch_pdu_metrics
from .backends import get_pdu_client
from .backends.base import PDUClientError
from .choices import OutletStatusChoices, SyncStatusChoices

logger = logging.getLogger(__name__)


def _epoch_to_dt(epoch):
    """Convert epoch seconds to an aware datetime, or None."""
    if epoch is None:
        return None
    try:
        return datetime.fromtimestamp(float(epoch), tz=UTC)
    except (ValueError, OSError):
        return None


#
# ManagedPDU views
#


@register_model_view(models.ManagedPDU)
class ManagedPDUView(generic.ObjectView):
    queryset = models.ManagedPDU.objects.all()

    def get_extra_context(self, request, instance):
        outlets = instance.outlets.restrict(request.user, "view").order_by("outlet_number")
        outlets_table = tables.PDUOutletTable(outlets)
        outlets_table.columns.hide("managed_pdu")
        outlets_table.configure(request)
        if request.user.has_perm("netbox_pdu_plugin.change_managedpdu"):
            outlets_table.columns.show("pk")  # Show checkbox for bulk actions
        else:
            outlets_table.columns.hide("pk")

        inlets = instance.inlets.restrict(request.user, "view").order_by("inlet_number")
        inlets_table = tables.PDUInletTable(inlets)
        inlets_table.columns.hide("managed_pdu")
        inlets_table.configure(request)

        ocps = list(instance.ocps.order_by("ocp_id"))

        return {
            "outlets_table": outlets_table,
            "outlet_count": outlets.count(),
            "inlets_table": inlets_table,
            "inlet_count": inlets.count(),
            "ocps": ocps,
        }


@register_model_view(models.ManagedPDU, name="list", path="", detail=False)
class ManagedPDUListView(generic.ObjectListView):
    queryset = models.ManagedPDU.objects.annotate(outlet_count=Count("outlets"))
    table = tables.ManagedPDUTable
    filterset = filtersets.ManagedPDUFilterSet
    filterset_form = forms.ManagedPDUFilterForm


@register_model_view(models.ManagedPDU, name="add", detail=False)
@register_model_view(models.ManagedPDU, name="edit")
class ManagedPDUEditView(generic.ObjectEditView):
    queryset = models.ManagedPDU.objects.all()
    form = forms.ManagedPDUForm


@register_model_view(models.ManagedPDU, name="delete")
class ManagedPDUDeleteView(generic.ObjectDeleteView):
    queryset = models.ManagedPDU.objects.all()


@register_model_view(models.ManagedPDU, name="sync")
class ManagedPDUSyncView(View):
    """
    View that synchronizes outlet, inlet, and hardware info from the PDU.
    Accepts POST requests only.
    """

    def post(self, request, pk):
        managed_pdu = get_object_or_404(models.ManagedPDU, pk=pk)

        if not request.user.has_perm("netbox_pdu_plugin.change_managedpdu"):
            messages.error(request, _("You do not have permission to sync this PDU."))
            return redirect(managed_pdu.get_absolute_url())

        client = get_pdu_client(managed_pdu)

        try:
            with transaction.atomic():
                now = timezone.now()

                # Sync PDU hardware info
                pdu_info = client.get_pdu_info()
                managed_pdu.pdu_model = pdu_info.get("model", "")
                managed_pdu.serial_number = pdu_info.get("serial_number", "")
                managed_pdu.firmware_version = pdu_info.get("firmware_version", "")
                managed_pdu.rated_voltage = pdu_info.get("rated_voltage", "")
                managed_pdu.rated_current = pdu_info.get("rated_current", "")
                managed_pdu.rated_frequency = pdu_info.get("rated_frequency", "")
                managed_pdu.rated_power = pdu_info.get("rated_power", "")
                managed_pdu.hw_revision = pdu_info.get("hw_revision", "")
                managed_pdu.pdu_mac_address = pdu_info.get("pdu_mac_address", "")
                managed_pdu.dns_servers = pdu_info.get("dns_servers", "")
                managed_pdu.default_gateway = pdu_info.get("default_gateway", "")
                managed_pdu.device_time = _epoch_to_dt(pdu_info.get("device_time_epoch"))
                managed_pdu.ntp_servers = pdu_info.get("ntp_servers", "")

                # Sync serial number to Device
                serial = pdu_info.get("serial_number", "")
                if serial and managed_pdu.device.serial != serial:
                    managed_pdu.device.serial = serial
                    managed_pdu.device.save(update_fields=["serial"])
                    logger.info("Updated Device serial [%s]: %s", managed_pdu.device, serial)

                models.PDUNetworkInterface.objects.filter(managed_pdu=managed_pdu).delete()
                for iface in pdu_info.get("network_interfaces", []):
                    models.PDUNetworkInterface.objects.create(
                        managed_pdu=managed_pdu,
                        interface_name=iface.get("name", ""),
                        mac_address=iface.get("mac_address", ""),
                        ip_address=iface.get("ip_address", ""),
                        config_method=iface.get("config_method", ""),
                        link_speed=iface.get("link_speed", ""),
                    )

                # Sync outlets
                outlet_data_list = client.get_all_outlet_data()
                outlet_created = 0
                outlet_updated = 0

                for outlet_data in outlet_data_list:
                    outlet_number = outlet_data["outlet_number"]
                    switching_state = outlet_data.get("switchingState", "unknown").lower()
                    if switching_state == "on":
                        status = OutletStatusChoices.ON
                    elif switching_state == "off":
                        status = OutletStatusChoices.OFF
                    else:
                        status = OutletStatusChoices.UNKNOWN

                    obj, created = models.PDUOutlet.objects.update_or_create(
                        managed_pdu=managed_pdu,
                        outlet_number=outlet_number,
                        defaults={
                            "outlet_name": outlet_data.get("name") or outlet_data.get("label", ""),
                            "status": status,
                            "current_a": outlet_data.get("current_a"),
                            "power_w": outlet_data.get("power_w"),
                            "voltage_v": outlet_data.get("voltage_v"),
                            "power_factor": outlet_data.get("power_factor"),
                            "energy_wh": outlet_data.get("energy_wh"),
                            "energy_reset_at": _epoch_to_dt(outlet_data.get("energy_reset_epoch")),
                            "last_updated_from_pdu": now,
                        },
                    )
                    if created:
                        outlet_created += 1
                    else:
                        outlet_updated += 1

                # Sync connected_device from NetBox PowerOutlet cable connections
                nb_outlets = PowerOutlet.objects.filter(device=managed_pdu.device)
                for nb_outlet in nb_outlets:
                    m = re.search(r"\d+", nb_outlet.name)
                    if not m:
                        continue
                    outlet_num = int(m.group())
                    peers = nb_outlet.link_peers
                    connected = peers[0].device if peers else None
                    models.PDUOutlet.objects.filter(
                        managed_pdu=managed_pdu,
                        outlet_number=outlet_num,
                    ).update(connected_device=connected)

                # Sync inlets
                inlet_data_list = client.get_all_inlet_data()
                inlet_created = 0
                inlet_updated = 0

                for inlet_data in inlet_data_list:
                    obj, created = models.PDUInlet.objects.update_or_create(
                        managed_pdu=managed_pdu,
                        inlet_number=inlet_data["inlet_number"],
                        defaults={
                            "inlet_name": inlet_data.get("name", ""),
                            "current_a": inlet_data.get("current_a"),
                            "power_w": inlet_data.get("power_w"),
                            "apparent_power_va": inlet_data.get("apparent_power_va"),
                            "voltage_v": inlet_data.get("voltage_v"),
                            "power_factor": inlet_data.get("power_factor"),
                            "frequency_hz": inlet_data.get("frequency_hz"),
                            "energy_wh": inlet_data.get("energy_wh"),
                            "energy_reset_at": _epoch_to_dt(inlet_data.get("energy_reset_epoch")),
                            "last_updated_from_pdu": now,
                        },
                    )
                    if created:
                        inlet_created += 1
                    else:
                        inlet_updated += 1

                managed_pdu.last_synced = now
                managed_pdu.sync_status = SyncStatusChoices.SUCCESS
                managed_pdu.save()

            messages.success(
                request,
                f"PDU sync complete: outlets {outlet_created} created, {outlet_updated} updated; "
                f"inlets {inlet_created} created, {inlet_updated} updated.",
            )
            logger.info(
                "PDU sync succeeded [%s]: outlets(created=%d, updated=%d) inlets(created=%d, updated=%d)",
                managed_pdu,
                outlet_created,
                outlet_updated,
                inlet_created,
                inlet_updated,
            )

        except PDUClientError as e:
            managed_pdu.sync_status = SyncStatusChoices.FAILED
            managed_pdu.save(update_fields=["sync_status"])
            messages.error(request, f"PDU sync error: {e}")
            logger.error("PDU sync failed [%s]: %s", managed_pdu, e)

        return redirect(managed_pdu.get_absolute_url())


class ManagedPDUGetMetricsView(View):
    """
    Fetch outlet/inlet metrics from the Prometheus endpoint and update metric
    fields only. Does not touch outlet status, energy_reset_at, or PDU hardware
    info. Only available for backends that support Prometheus metrics.
    """

    def post(self, request, pk):
        managed_pdu = get_object_or_404(models.ManagedPDU, pk=pk)

        if not request.user.has_perm("netbox_pdu_plugin.change_managedpdu"):
            messages.error(request, _("You do not have permission to update metrics."))
            return redirect(managed_pdu.get_absolute_url())

        try:
            outlet_updated, inlet_updated, ocp_updated = fetch_pdu_metrics(managed_pdu)
            messages.success(
                request,
                f"Metrics updated: {outlet_updated} outlets, {inlet_updated} inlets, {ocp_updated} OCPs.",
            )
            logger.info(
                "Metrics fetch succeeded [%s]: outlets=%d inlets=%d ocps=%d",
                managed_pdu,
                outlet_updated,
                inlet_updated,
                ocp_updated,
            )
        except PDUClientError as e:
            from .choices import SyncStatusChoices
            managed_pdu.metrics_status = SyncStatusChoices.FAILED
            managed_pdu.save(update_fields=["metrics_status"])
            messages.error(request, f"Metrics fetch error: {e}")
            logger.error("Metrics fetch failed [%s]: %s", managed_pdu, e)

        return redirect(managed_pdu.get_absolute_url())


#
# PDUOutlet views
#


@register_model_view(models.PDUOutlet, name="sync")
class PDUOutletSyncView(View):
    """View that synchronizes a single outlet."""

    def post(self, request, pk):
        outlet = get_object_or_404(models.PDUOutlet, pk=pk)
        managed_pdu = outlet.managed_pdu

        if not request.user.has_perm("netbox_pdu_plugin.change_managedpdu"):
            messages.error(request, _("You do not have permission to sync this PDU."))
            return redirect(outlet.get_absolute_url())

        client = get_pdu_client(managed_pdu)

        try:
            outlet_data = client.get_single_outlet_data(outlet.outlet_number - 1)
            switching_state = outlet_data.get("switchingState", "unknown").lower()
            if switching_state == "on":
                status = OutletStatusChoices.ON
            elif switching_state == "off":
                status = OutletStatusChoices.OFF
            else:
                status = OutletStatusChoices.UNKNOWN

            outlet.outlet_name = outlet_data.get("name") or outlet_data.get("label", "") or outlet.outlet_name
            outlet.status = status
            outlet.current_a = outlet_data.get("current_a")
            outlet.power_w = outlet_data.get("power_w")
            outlet.voltage_v = outlet_data.get("voltage_v")
            outlet.power_factor = outlet_data.get("power_factor")
            outlet.energy_wh = outlet_data.get("energy_wh")
            outlet.energy_reset_at = _epoch_to_dt(outlet_data.get("energy_reset_epoch"))
            outlet.last_updated_from_pdu = timezone.now()
            outlet.save()

            messages.success(request, f"Outlet {outlet.outlet_number} synced successfully.")
            logger.info("Outlet sync succeeded [%s]", outlet)

        except PDUClientError as e:
            messages.error(request, f"Sync error: {e}")
            logger.error("Outlet sync failed [%s]: %s", outlet, e)

        return redirect(request.META.get("HTTP_REFERER") or outlet.get_absolute_url())


@register_model_view(models.PDUOutlet)
class PDUOutletView(generic.ObjectView):
    queryset = models.PDUOutlet.objects.all()

    def get_extra_context(self, request, instance):
        thresholds = []
        try:
            client = get_pdu_client(instance.managed_pdu)
            thresholds = client.get_outlet_thresholds(instance.outlet_number - 1)
        except PDUClientError:
            pass
        return {"thresholds": thresholds}


@register_model_view(models.PDUOutlet, name="list", path="", detail=False)
class PDUOutletListView(generic.ObjectListView):
    queryset = models.PDUOutlet.objects.select_related("managed_pdu", "connected_device")
    table = tables.PDUOutletTable
    filterset = filtersets.PDUOutletFilterSet
    filterset_form = forms.PDUOutletFilterForm


class PDUOutletPowerView(View):
    """Base view for outlet power control (on/off/cycle)."""

    power_state = None  # 'on', 'off', or 'cycle'

    def post(self, request, pk):
        outlet = get_object_or_404(models.PDUOutlet, pk=pk)
        managed_pdu = outlet.managed_pdu

        if not request.user.has_perm("netbox_pdu_plugin.change_managedpdu"):
            messages.error(request, _("You do not have permission to control this outlet."))
            return redirect(request.META.get("HTTP_REFERER") or outlet.get_absolute_url())

        client = get_pdu_client(managed_pdu)

        try:
            outlet_index = outlet.outlet_number - 1
            client.set_outlet_power_state(outlet_index, self.power_state)
            label = {"on": "ON", "off": "OFF", "cycle": "Cycle"}.get(self.power_state, self.power_state)

            if self.power_state == "cycle":
                # Enqueue a background job to fetch the status 5 seconds later
                queue = django_rq.get_queue("default")
                queue.enqueue_in(
                    timedelta(seconds=5),
                    jobs.update_outlet_status,
                    outlet.pk,
                    managed_pdu.api_url,
                    managed_pdu.api_username,
                    managed_pdu.api_password,
                    managed_pdu.verify_ssl,
                    outlet_index,
                )
                messages.success(
                    request, f"Outlet {outlet.outlet_number}: Cycle command sent. Status will update in ~5 seconds."
                )
                logger.info("Outlet cycle sent [%s], status update scheduled in 5s", outlet)
            else:
                # Fetch the updated power state immediately and save to DB
                new_state = client.get_outlet_power_state_by_index(outlet_index)
                state_map = {"on": OutletStatusChoices.ON, "off": OutletStatusChoices.OFF}
                outlet.status = state_map.get(new_state, OutletStatusChoices.UNKNOWN)
                outlet.last_updated_from_pdu = timezone.now()
                outlet.save()
                messages.success(
                    request, f"Outlet {outlet.outlet_number}: power {label} — status updated to {new_state.upper()}."
                )
                logger.info("Outlet power %s sent [%s], new state: %s", self.power_state, outlet, new_state)
        except PDUClientError as e:
            messages.error(request, f"Power control error: {e}")
            logger.error("Outlet power %s failed [%s]: %s", self.power_state, outlet, e)

        return redirect(request.META.get("HTTP_REFERER") or outlet.get_absolute_url())


@register_model_view(models.PDUOutlet, name="power_on")
class PDUOutletPowerOnView(PDUOutletPowerView):
    """Turn on a single outlet."""

    power_state = "on"


@register_model_view(models.PDUOutlet, name="power_off")
class PDUOutletPowerOffView(PDUOutletPowerView):
    """Turn off a single outlet."""

    power_state = "off"


@register_model_view(models.PDUOutlet, name="power_cycle")
class PDUOutletPowerCycleView(PDUOutletPowerView):
    """Cycle (off then on) a single outlet."""

    power_state = "cycle"


class PDUOutletBulkPowerView(View):
    """Bulk power ON/OFF for multiple outlets of a single PDU."""

    def post(self, request, pk):
        managed_pdu = get_object_or_404(models.ManagedPDU, pk=pk)

        if not request.user.has_perm("netbox_pdu_plugin.change_managedpdu"):
            messages.error(request, _("You do not have permission to control outlets."))
            return redirect(managed_pdu.get_absolute_url())

        action = request.POST.get("action")
        if action not in ("on", "off"):
            messages.error(request, _("Invalid action."))
            return redirect(managed_pdu.get_absolute_url())

        outlet_pks = request.POST.getlist("pk")
        if not outlet_pks:
            messages.warning(request, _("No outlets selected."))
            return redirect(managed_pdu.get_absolute_url())

        outlets = models.PDUOutlet.objects.filter(pk__in=outlet_pks, managed_pdu=managed_pdu)
        client = get_pdu_client(managed_pdu)
        success, failed = 0, 0

        for outlet in outlets:
            try:
                client.set_outlet_power_state(outlet.outlet_number - 1, action)
                # Optimistic status update — avoids N extra API round-trips.
                # Use individual outlet sync to verify actual state if needed.
                outlet.status = OutletStatusChoices.ON if action == "on" else OutletStatusChoices.OFF
                outlet.last_updated_from_pdu = timezone.now()
                outlet.save()
                success += 1
            except PDUClientError as e:
                logger.error("Bulk power %s failed for outlet %s: %s", action, outlet, e)
                failed += 1

        if success:
            messages.success(request, f"{success} outlet(s) powered {action.upper()}.")
        if failed:
            messages.error(request, f"{failed} outlet(s) failed.")

        return redirect(managed_pdu.get_absolute_url())


@register_model_view(models.PDUOutlet, name="add", detail=False)
@register_model_view(models.PDUOutlet, name="edit")
class PDUOutletEditView(generic.ObjectEditView):
    queryset = models.PDUOutlet.objects.all()
    form = forms.PDUOutletForm


@register_model_view(models.PDUOutlet, name="delete")
class PDUOutletDeleteView(generic.ObjectDeleteView):
    queryset = models.PDUOutlet.objects.all()


@register_model_view(models.PDUOutlet, name="push_name")
class PDUOutletPushNameView(View):
    """Push outlet_name from NetBox to the PDU."""

    def post(self, request, pk):
        outlet = get_object_or_404(models.PDUOutlet, pk=pk)

        if not request.user.has_perm("netbox_pdu_plugin.change_managedpdu"):
            messages.error(request, _("You do not have permission to update this PDU."))
            return redirect(request.META.get("HTTP_REFERER") or outlet.get_absolute_url())

        client = get_pdu_client(outlet.managed_pdu)
        push_succeeded = False
        try:
            client.set_outlet_name(outlet.outlet_number - 1, outlet.outlet_name)
            push_succeeded = True
            messages.success(
                request,
                f'Outlet {outlet.outlet_number}: name "{outlet.outlet_name}" pushed to PDU.',
            )
            logger.info("Pushed name to PDU outlet [%s]: %r", outlet, outlet.outlet_name)
        except PDUClientError as e:
            messages.error(request, f"Failed to push name: {e}")
            logger.error("Push name failed [%s]: %s", outlet, e)

        # Update the label of the matching NetBox PowerOutlet only when the PDU push succeeded
        if push_succeeded:
            for po in PowerOutlet.objects.filter(device=outlet.managed_pdu.device):
                m = re.search(r"\d+", po.name)
                if m and int(m.group()) == outlet.outlet_number:
                    po.label = outlet.outlet_name
                    po.save(update_fields=["label"])
                    messages.info(request, f'PowerOutlet "{po.name}" label updated to "{outlet.outlet_name}".')
                    break

        return redirect(request.META.get("HTTP_REFERER") or outlet.get_absolute_url())


#
# PDUInlet views
#


@register_model_view(models.PDUInlet, name="sync")
class PDUInletSyncView(View):
    """View that synchronizes a single inlet."""

    def post(self, request, pk):
        inlet = get_object_or_404(models.PDUInlet, pk=pk)
        managed_pdu = inlet.managed_pdu

        if not request.user.has_perm("netbox_pdu_plugin.change_managedpdu"):
            messages.error(request, _("You do not have permission to sync this PDU."))
            return redirect(inlet.get_absolute_url())

        client = get_pdu_client(managed_pdu)

        try:
            inlet_data = client.get_single_inlet_data(inlet.inlet_number - 1)
            inlet.inlet_name = inlet_data.get("name", "") or inlet.inlet_name
            inlet.current_a = inlet_data.get("current_a")
            inlet.power_w = inlet_data.get("power_w")
            inlet.apparent_power_va = inlet_data.get("apparent_power_va")
            inlet.voltage_v = inlet_data.get("voltage_v")
            inlet.power_factor = inlet_data.get("power_factor")
            inlet.frequency_hz = inlet_data.get("frequency_hz")
            inlet.energy_wh = inlet_data.get("energy_wh")
            inlet.energy_reset_at = _epoch_to_dt(inlet_data.get("energy_reset_epoch"))
            inlet.last_updated_from_pdu = timezone.now()
            inlet.save()

            messages.success(request, f"Inlet {inlet.inlet_number} synced successfully.")
            logger.info("Inlet sync succeeded [%s]", inlet)

        except PDUClientError as e:
            messages.error(request, f"Sync error: {e}")
            logger.error("Inlet sync failed [%s]: %s", inlet, e)

        return redirect(request.META.get("HTTP_REFERER") or inlet.get_absolute_url())


@register_model_view(models.PDUInlet, name="push_name")
class PDUInletPushNameView(View):
    """Push inlet_name from NetBox to the PDU."""

    def post(self, request, pk):
        inlet = get_object_or_404(models.PDUInlet, pk=pk)

        if not request.user.has_perm("netbox_pdu_plugin.change_managedpdu"):
            messages.error(request, _("You do not have permission to update this PDU."))
            return redirect(request.META.get("HTTP_REFERER") or inlet.get_absolute_url())

        if not inlet.inlet_name:
            messages.warning(request, "Inlet name is empty — nothing to push.")
            return redirect(request.META.get("HTTP_REFERER") or inlet.get_absolute_url())

        client = get_pdu_client(inlet.managed_pdu)
        push_succeeded = False
        try:
            client.set_inlet_name(inlet.inlet_number - 1, inlet.inlet_name)
            push_succeeded = True
            messages.success(
                request,
                f'Inlet {inlet.inlet_number}: name "{inlet.inlet_name}" pushed to PDU.',
            )
        except PDUClientError as e:
            messages.error(request, f"Failed to push inlet name: {e}")

        # Update the label of the matching NetBox PowerPort only when the PDU push succeeded
        if push_succeeded:
            for pp in PowerPort.objects.filter(device=inlet.managed_pdu.device):
                m = re.search(r"\d+", pp.name)
                if m and int(m.group()) == inlet.inlet_number:
                    pp.label = inlet.inlet_name
                    pp.save(update_fields=["label"])
                    messages.info(request, f'PowerPort "{pp.name}" label updated to "{inlet.inlet_name}".')
                    break

        return redirect(request.META.get("HTTP_REFERER") or inlet.get_absolute_url())


@register_model_view(models.PDUInlet)
class PDUInletView(generic.ObjectView):
    queryset = models.PDUInlet.objects.all()

    def get_extra_context(self, request, instance):
        thresholds = []
        try:
            client = get_pdu_client(instance.managed_pdu)
            thresholds = client.get_inlet_thresholds(instance.inlet_number - 1)
        except PDUClientError:
            pass
        linepairs = list(
            models.PDUInletLinePair.objects.filter(
                managed_pdu=instance.managed_pdu,
                inlet_number=instance.inlet_number,
            ).order_by("line_pair")
        )
        return {"thresholds": thresholds, "linepairs": linepairs}


@register_model_view(models.PDUInlet, name="edit")
class PDUInletEditView(generic.ObjectEditView):
    queryset = models.PDUInlet.objects.all()
    form = forms.PDUInletForm


@register_model_view(models.PDUInlet, name="list", path="", detail=False)
class PDUInletListView(generic.ObjectListView):
    queryset = models.PDUInlet.objects.select_related("managed_pdu")
    table = tables.PDUInletTable
    filterset = filtersets.PDUInletFilterSet
    filterset_form = forms.PDUInletFilterForm
