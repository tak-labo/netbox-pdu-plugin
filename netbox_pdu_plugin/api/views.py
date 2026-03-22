from django.db.models import Count
from netbox.api.viewsets import NetBoxModelViewSet

from .. import filtersets, models
from .serializers import ManagedPDUSerializer, PDUInletSerializer, PDUOutletSerializer


class ManagedPDUViewSet(NetBoxModelViewSet):
    queryset = models.ManagedPDU.objects.annotate(
        outlet_count=Count('outlets')
    ).prefetch_related('tags')
    serializer_class = ManagedPDUSerializer
    filterset_class = filtersets.ManagedPDUFilterSet


class PDUOutletViewSet(NetBoxModelViewSet):
    queryset = models.PDUOutlet.objects.select_related(
        'managed_pdu', 'connected_device'
    ).prefetch_related('tags')
    serializer_class = PDUOutletSerializer
    filterset_class = filtersets.PDUOutletFilterSet


class PDUInletViewSet(NetBoxModelViewSet):
    queryset = models.PDUInlet.objects.select_related('managed_pdu').prefetch_related('tags')
    serializer_class = PDUInletSerializer
    filterset_class = filtersets.PDUInletFilterSet
