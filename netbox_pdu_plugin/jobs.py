import logging

from django.utils import timezone

from .backends import get_pdu_client
from .choices import OutletStatusChoices

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
        state_map = {'on': OutletStatusChoices.ON, 'off': OutletStatusChoices.OFF}

        outlet.status = state_map.get(new_state, OutletStatusChoices.UNKNOWN)
        outlet.last_updated_from_pdu = timezone.now()
        outlet.save()

        logger.info('Background status update for outlet pk=%s: %s', outlet_pk, new_state)
    except Exception as e:
        logger.error('Background status update failed for outlet pk=%s: %s', outlet_pk, e)
