import strawberry
import strawberry_django

from .types import ManagedPDUType, PDUInletType, PDUOutletType


@strawberry.type(name='Query')
class NetBoxMgmtPDUQuery:
    managed_pdu: ManagedPDUType = strawberry_django.field()
    managed_pdu_list: list[ManagedPDUType] = strawberry_django.field()
    pdu_outlet: PDUOutletType = strawberry_django.field()
    pdu_outlet_list: list[PDUOutletType] = strawberry_django.field()
    pdu_inlet: PDUInletType = strawberry_django.field()
    pdu_inlet_list: list[PDUInletType] = strawberry_django.field()
