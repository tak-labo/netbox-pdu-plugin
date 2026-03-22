from typing import TYPE_CHECKING, Annotated

import strawberry
import strawberry_django
from netbox.graphql.filters import NetBoxModelFilter
from strawberry import ID

from .. import models

if TYPE_CHECKING:
    from .enums import OutletStatusEnum, SyncStatusEnum


@strawberry_django.filter_type(models.ManagedPDU, lookups=True)
class ManagedPDUFilter(NetBoxModelFilter):
    sync_status: Annotated['SyncStatusEnum', strawberry.lazy('netbox_pdu_plugin.graphql.enums')] | None = (
        strawberry_django.filter_field()
    )


@strawberry_django.filter_type(models.PDUOutlet, lookups=True)
class PDUOutletFilter(NetBoxModelFilter):
    managed_pdu: Annotated['ManagedPDUFilter', strawberry.lazy('netbox_pdu_plugin.graphql.filters')] | None = (
        strawberry_django.filter_field()
    )
    managed_pdu_id: ID | None = strawberry_django.filter_field()
    status: Annotated['OutletStatusEnum', strawberry.lazy('netbox_pdu_plugin.graphql.enums')] | None = (
        strawberry_django.filter_field()
    )


@strawberry_django.filter_type(models.PDUInlet, lookups=True)
class PDUInletFilter(NetBoxModelFilter):
    managed_pdu: Annotated['ManagedPDUFilter', strawberry.lazy('netbox_pdu_plugin.graphql.filters')] | None = (
        strawberry_django.filter_field()
    )
    managed_pdu_id: ID | None = strawberry_django.filter_field()
