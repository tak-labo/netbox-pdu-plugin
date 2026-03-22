from netbox.search import SearchIndex, register_search

from .models import ManagedPDU, PDUOutlet


@register_search
class ManagedPDUIndex(SearchIndex):
    model = ManagedPDU
    fields = (
        ('api_url', 500),
        ('comments', 5000),
    )
    display_attrs = ('device', 'api_url', 'sync_status')


@register_search
class PDUOutletIndex(SearchIndex):
    model = PDUOutlet
    fields = (
        ('outlet_name', 100),
        ('comments', 5000),
    )
    display_attrs = ('managed_pdu', 'outlet_number', 'outlet_name', 'status')
