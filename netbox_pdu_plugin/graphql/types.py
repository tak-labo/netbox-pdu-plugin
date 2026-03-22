from typing import TYPE_CHECKING, Annotated

import strawberry
import strawberry_django
from netbox.graphql.types import NetBoxObjectType

from .. import models
from . import filters

if TYPE_CHECKING:
    from dcim.graphql.types import DeviceType


@strawberry_django.type(models.ManagedPDU, fields='__all__', filters=filters.ManagedPDUFilter)
class ManagedPDUType(NetBoxObjectType):
    device: Annotated['DeviceType', strawberry.lazy('dcim.graphql.types')]
    outlets: list[Annotated['PDUOutletType', strawberry.lazy('netbox_pdu_plugin.graphql.types')]]


@strawberry_django.type(models.PDUOutlet, fields='__all__', filters=filters.PDUOutletFilter)
class PDUOutletType(NetBoxObjectType):
    managed_pdu: Annotated['ManagedPDUType', strawberry.lazy('netbox_pdu_plugin.graphql.types')]
    connected_device: Annotated['DeviceType', strawberry.lazy('dcim.graphql.types')] | None


@strawberry_django.type(models.PDUInlet, fields='__all__', filters=filters.PDUInletFilter)
class PDUInletType(NetBoxObjectType):
    managed_pdu: Annotated['ManagedPDUType', strawberry.lazy('netbox_pdu_plugin.graphql.types')]
