import django_filters
from django.utils.translation import gettext_lazy as _
from netbox.filtersets import NetBoxModelFilterSet
from utilities.filtersets import register_filterset

from .choices import OutletStatusChoices, SyncStatusChoices
from .models import ManagedPDU, PDUInlet, PDUOutlet


@register_filterset
class ManagedPDUFilterSet(NetBoxModelFilterSet):
    sync_status = django_filters.MultipleChoiceFilter(
        choices=SyncStatusChoices,
        label=_('Sync Status'),
    )

    class Meta:
        model = ManagedPDU
        fields = ('id', 'device', 'sync_status')

    def search(self, queryset, name, value):
        return queryset.filter(device__name__icontains=value)


@register_filterset
class PDUOutletFilterSet(NetBoxModelFilterSet):
    managed_pdu_id = django_filters.ModelMultipleChoiceFilter(
        field_name='managed_pdu',
        queryset=ManagedPDU.objects.all(),
        label=_('Managed PDU (ID)'),
    )
    status = django_filters.MultipleChoiceFilter(
        choices=OutletStatusChoices,
        label=_('Status'),
    )

    class Meta:
        model = PDUOutlet
        fields = ('id', 'managed_pdu', 'outlet_number', 'status', 'connected_device')

    def search(self, queryset, name, value):
        return queryset.filter(outlet_name__icontains=value)


@register_filterset
class PDUInletFilterSet(NetBoxModelFilterSet):
    managed_pdu_id = django_filters.ModelMultipleChoiceFilter(
        field_name='managed_pdu',
        queryset=ManagedPDU.objects.all(),
        label=_('Managed PDU (ID)'),
    )

    class Meta:
        model = PDUInlet
        fields = ('id', 'managed_pdu', 'inlet_number')

    def search(self, queryset, name, value):
        return queryset.filter(inlet_name__icontains=value)
