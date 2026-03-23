import logging

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .backends import get_pdu_client
from .backends.base import PDUClientError
from .choices import OutletStatusChoices, SyncStatusChoices

logger = logging.getLogger(__name__)


def update_outlet_status(outlet_pk, api_url, username, password, verify_ssl, outlet_index):
    """
    Background job: fetch outlet power state from PDU and save to DB.
    Intended to be enqueued after a power cycle command.
    """
    from .models import PDUOutlet

    try:
        outlet = PDUOutlet.objects.get(pk=outlet_pk)
        client = get_pdu_client(outlet.managed_pdu)
        new_state = client.get_outlet_power_state_by_index(outlet_index)
        state_map = {"on": OutletStatusChoices.ON, "off": OutletStatusChoices.OFF}

        outlet.status = state_map.get(new_state, OutletStatusChoices.UNKNOWN)
        outlet.last_updated_from_pdu = timezone.now()
        outlet.save()

        logger.info("Background status update for outlet pk=%s: %s", outlet_pk, new_state)
    except Exception as e:
        logger.error("Background status update failed for outlet pk=%s: %s", outlet_pk, e)


def fetch_pdu_metrics(managed_pdu):
    """
    Fetch Prometheus metrics for a single ManagedPDU and save to DB.
    Returns (outlet_updated, inlet_updated, ocp_updated) counts.
    Raises PDUClientError if the backend does not support Prometheus metrics or fetch fails.
    """
    from . import models

    client = get_pdu_client(managed_pdu)
    if not client.supports_prometheus_metrics:
        raise PDUClientError("Backend does not support Prometheus metrics")

    now = timezone.now()
    data = client.get_all_metrics_prometheus()

    with transaction.atomic():
        outlet_updated = 0
        for outlet_data in data.get("outlets", []):
            update_fields = {
                "current_a": outlet_data.get("current_a"),
                "power_w": outlet_data.get("power_w"),
                "apparent_power_va": outlet_data.get("apparent_power_va"),
                "voltage_v": outlet_data.get("voltage_v"),
                "power_factor": outlet_data.get("power_factor"),
                "energy_wh": outlet_data.get("energy_wh"),
                "last_updated_from_pdu": now,
            }
            if outlet_data.get("name"):
                update_fields["outlet_name"] = outlet_data["name"]
            outlet_updated += models.PDUOutlet.objects.filter(
                managed_pdu=managed_pdu,
                outlet_number=outlet_data["outlet_number"],
            ).update(**update_fields)

        inlet_updated = 0
        for inlet_data in data.get("inlets", []):
            inlet_number = inlet_data["inlet_number"]
            update_fields = {
                "current_a": inlet_data.get("current_a"),
                "power_w": inlet_data.get("power_w"),
                "apparent_power_va": inlet_data.get("apparent_power_va"),
                "voltage_v": inlet_data.get("voltage_v"),
                "power_factor": inlet_data.get("power_factor"),
                "frequency_hz": inlet_data.get("frequency_hz"),
                "energy_wh": inlet_data.get("energy_wh"),
                # 3-phase poleline and unbalance
                "poleline_l1_current_a": inlet_data.get("poleline_l1_current_a"),
                "poleline_l2_current_a": inlet_data.get("poleline_l2_current_a"),
                "poleline_l3_current_a": inlet_data.get("poleline_l3_current_a"),
                "unbalanced_current_pct": inlet_data.get("unbalanced_current_pct"),
                "unbalanced_ll_current_pct": inlet_data.get("unbalanced_ll_current_pct"),
                "unbalanced_ll_voltage_pct": inlet_data.get("unbalanced_ll_voltage_pct"),
                "last_updated_from_pdu": now,
            }
            if inlet_data.get("name"):
                update_fields["inlet_name"] = inlet_data["name"]
            inlet_updated += models.PDUInlet.objects.filter(
                managed_pdu=managed_pdu,
                inlet_number=inlet_number,
            ).update(**update_fields)

            # Linepairs: replace entirely (delete + recreate)
            models.PDUInletLinePair.objects.filter(
                managed_pdu=managed_pdu,
                inlet_number=inlet_number,
            ).delete()
            for lp in inlet_data.get("linepairs", []):
                models.PDUInletLinePair.objects.create(
                    managed_pdu=managed_pdu,
                    inlet_number=inlet_number,
                    line_pair=lp["line_pair"],
                    voltage_v=lp.get("voltage_v"),
                    current_a=lp.get("current_a"),
                    power_w=lp.get("power_w"),
                    apparent_power_va=lp.get("apparent_power_va"),
                    power_factor=lp.get("power_factor"),
                    energy_wh=lp.get("energy_wh"),
                    last_updated_from_pdu=now,
                )

        ocp_updated = 0
        for ocp_data in data.get("ocps", []):
            models.PDUOverCurrentProtector.objects.update_or_create(
                managed_pdu=managed_pdu,
                ocp_id=ocp_data["ocp_id"],
                defaults={
                    "rating_current_a": ocp_data.get("rating_current_a"),
                    "current_a": ocp_data.get("current_a"),
                    "poleline_l1_current_a": ocp_data.get("poleline_l1_current_a"),
                    "poleline_l2_current_a": ocp_data.get("poleline_l2_current_a"),
                    "poleline_l3_current_a": ocp_data.get("poleline_l3_current_a"),
                    "tripped": ocp_data.get("tripped"),
                    "last_updated_from_pdu": now,
                },
            )
            ocp_updated += 1

    managed_pdu.last_metrics_fetched = now
    managed_pdu.metrics_status = SyncStatusChoices.SUCCESS
    managed_pdu.save(update_fields=["last_metrics_fetched", "metrics_status"])

    return outlet_updated, inlet_updated, ocp_updated


_metrics_interval = settings.PLUGINS_CONFIG.get("netbox_pdu_plugin", {}).get("metrics_poll_interval", 0)

if _metrics_interval > 0:
    from netbox.jobs import JobRunner, system_job

    @system_job(interval=_metrics_interval)
    class PDUGetMetricsJob(JobRunner):
        class Meta:
            name = "PDU Get Metrics"

        def run(self, *args, **kwargs):
            from . import models

            pdus = models.ManagedPDU.objects.all()
            success, failed = 0, 0
            for pdu in pdus:
                try:
                    outlet_updated, inlet_updated, ocp_updated = fetch_pdu_metrics(pdu)
                    self.logger.info(
                        f"Metrics fetched [{pdu}]: outlets={outlet_updated} inlets={inlet_updated} ocps={ocp_updated}"
                    )
                    success += 1
                except Exception as e:
                    self.logger.error(f"Metrics fetch failed [{pdu}]: {e}")
                    pdu.metrics_status = SyncStatusChoices.FAILED
                    pdu.save(update_fields=["metrics_status"])
                    failed += 1
            self.logger.info(f"Periodic metrics complete: {success} OK, {failed} failed")
