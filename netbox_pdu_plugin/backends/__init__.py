from .base import BasePDUClient, PDUClientError
from .raritan import RaritanPDUClient
from .unifi import UniFiPDUClient

_VENDOR_BACKENDS = {
    'raritan': RaritanPDUClient,
    'ubiquiti': UniFiPDUClient,
}


def get_pdu_client(managed_pdu) -> BasePDUClient:
    """
    Return the appropriate PDU client for the given ManagedPDU instance.
    Raises PDUClientError if no backend is registered for the vendor.
    """
    backend_class = _VENDOR_BACKENDS.get(managed_pdu.vendor)
    if not backend_class:
        raise PDUClientError(f'No backend registered for vendor: {managed_pdu.vendor!r}')
    return backend_class(
        base_url=managed_pdu.api_url,
        username=managed_pdu.api_username,
        password=managed_pdu.api_password,
        verify_ssl=managed_pdu.verify_ssl,
        managed_pdu=managed_pdu,
    )
