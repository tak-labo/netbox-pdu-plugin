from dcim.models import Device
from django import forms
from django.utils.translation import gettext_lazy as _
from netbox.forms import NetBoxModelFilterSetForm, NetBoxModelForm
from utilities.forms.fields import (
    CommentField,
    DynamicModelChoiceField,
    DynamicModelMultipleChoiceField,
    TagFilterField,
)
from utilities.forms.rendering import FieldSet

from .choices import OutletStatusChoices, SyncStatusChoices
from .models import ManagedPDU, PDUInlet, PDUOutlet


class ManagedPDUForm(NetBoxModelForm):
    device = DynamicModelChoiceField(
        queryset=Device.objects.all(),
        help_text=_('Select the PDU device registered in NetBox'),
    )
    comments = CommentField()

    class Meta:
        model = ManagedPDU
        fields = (
            'device', 'vendor', 'api_url', 'api_username', 'api_password',
            'verify_ssl', 'comments', 'tags',
        )
        widgets = {
            'api_password': forms.PasswordInput(render_value=True),
        }


class ManagedPDUFilterForm(NetBoxModelFilterSetForm):
    model = ManagedPDU
    fieldsets = (
        FieldSet('q', 'filter_id', 'tag'),
        FieldSet('sync_status', name='Sync'),
    )
    sync_status = forms.MultipleChoiceField(
        choices=SyncStatusChoices,
        required=False,
        label=_('Sync Status'),
    )
    tag = TagFilterField(model)


class PDUOutletForm(NetBoxModelForm):
    managed_pdu = DynamicModelChoiceField(
        queryset=ManagedPDU.objects.all(),
        label=_('Managed PDU'),
    )
    connected_device = DynamicModelChoiceField(
        queryset=Device.objects.all(),
        required=False,
        label=_('Connected Device'),
        help_text=_('Device connected to this outlet'),
    )
    comments = CommentField()

    class Meta:
        model = PDUOutlet
        fields = (
            'managed_pdu', 'outlet_number', 'outlet_name',
            'connected_device', 'comments', 'tags',
        )


class PDUOutletFilterForm(NetBoxModelFilterSetForm):
    model = PDUOutlet
    fieldsets = (
        FieldSet('q', 'filter_id', 'tag'),
        FieldSet('managed_pdu_id', 'status', name='Outlet'),
    )
    managed_pdu_id = DynamicModelMultipleChoiceField(
        queryset=ManagedPDU.objects.all(),
        required=False,
        label=_('Managed PDU'),
    )
    status = forms.MultipleChoiceField(
        choices=OutletStatusChoices,
        required=False,
        label=_('Status'),
    )
    tag = TagFilterField(model)


class PDUInletForm(NetBoxModelForm):
    comments = CommentField()

    class Meta:
        model = PDUInlet
        fields = ('inlet_name', 'comments', 'tags')


class PDUInletFilterForm(NetBoxModelFilterSetForm):
    model = PDUInlet
    fieldsets = (
        FieldSet('q', 'filter_id', 'tag'),
        FieldSet('managed_pdu_id', name='Inlet'),
    )
    managed_pdu_id = DynamicModelMultipleChoiceField(
        queryset=ManagedPDU.objects.all(),
        required=False,
        label=_('Managed PDU'),
    )
    tag = TagFilterField(model)
