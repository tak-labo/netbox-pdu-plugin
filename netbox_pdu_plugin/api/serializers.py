from dcim.api.serializers import DeviceSerializer
from netbox.api.serializers import NetBoxModelSerializer
from rest_framework import serializers

from ..models import ManagedPDU, PDUInlet, PDUOutlet


class ManagedPDUSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(
        view_name='plugins-api:netbox_pdu_plugin-api:managedpdu-detail'
    )
    device = DeviceSerializer(nested=True)
    outlet_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = ManagedPDU
        fields = (
            'id', 'url', 'display', 'device', 'api_url', 'api_username',
            'verify_ssl', 'sync_status', 'last_synced', 'outlet_count',
            'comments', 'tags', 'custom_fields', 'created', 'last_updated',
        )
        brief_fields = ('id', 'url', 'display', 'device')
        # api_password is excluded from serialization for security


class PDUOutletSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(
        view_name='plugins-api:netbox_pdu_plugin-api:pduoutlet-detail'
    )
    managed_pdu = ManagedPDUSerializer(nested=True)
    connected_device = DeviceSerializer(nested=True, required=False, allow_null=True)

    class Meta:
        model = PDUOutlet
        fields = (
            'id', 'url', 'display', 'managed_pdu', 'outlet_number',
            'outlet_name', 'connected_device', 'status',
            'current_a', 'power_w', 'voltage_v', 'power_factor',
            'energy_wh', 'energy_reset_at', 'last_updated_from_pdu',
            'comments', 'tags', 'custom_fields', 'created', 'last_updated',
        )
        brief_fields = ('id', 'url', 'display', 'outlet_number', 'outlet_name')


class PDUInletSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(
        view_name='plugins-api:netbox_pdu_plugin-api:pduinlet-detail'
    )
    managed_pdu = ManagedPDUSerializer(nested=True)

    class Meta:
        model = PDUInlet
        fields = (
            'id', 'url', 'display', 'managed_pdu', 'inlet_number', 'inlet_name',
            'current_a', 'power_w', 'apparent_power_va', 'voltage_v',
            'power_factor', 'frequency_hz', 'energy_wh', 'energy_reset_at',
            'last_updated_from_pdu',
            'comments', 'tags', 'custom_fields', 'created', 'last_updated',
        )
        brief_fields = ('id', 'url', 'display', 'inlet_number', 'inlet_name')
