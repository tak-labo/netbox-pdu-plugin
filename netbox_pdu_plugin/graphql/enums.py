import strawberry

from ..choices import OutletStatusChoices, SyncStatusChoices

OutletStatusEnum = strawberry.enum(OutletStatusChoices.as_enum())
SyncStatusEnum = strawberry.enum(SyncStatusChoices.as_enum())
