from django.urls import include, path
from utilities.urls import get_model_urls

from . import views

urlpatterns = (
    # Managed PDU
    path(
        "managed-pdus/",
        include(get_model_urls("netbox_pdu_plugin", "managedpdu", detail=False)),
    ),
    path(
        "managed-pdus/<int:pk>/",
        include(get_model_urls("netbox_pdu_plugin", "managedpdu")),
    ),
    path(
        "managed-pdus/<int:pk>/sync/",
        views.ManagedPDUSyncView.as_view(),
        name="managedpdu_sync",
    ),
    path(
        "managed-pdus/<int:pk>/get-metrics/",
        views.ManagedPDUGetMetricsView.as_view(),
        name="managedpdu_get_metrics",
    ),
    path(
        "managed-pdus/<int:pk>/bulk-power/",
        views.PDUOutletBulkPowerView.as_view(),
        name="pduoutlet_bulk_power",
    ),
    # PDU Outlet
    path(
        "outlets/",
        include(get_model_urls("netbox_pdu_plugin", "pduoutlet", detail=False)),
    ),
    path(
        "outlets/<int:pk>/",
        include(get_model_urls("netbox_pdu_plugin", "pduoutlet")),
    ),
    path(
        "outlets/<int:pk>/sync/",
        views.PDUOutletSyncView.as_view(),
        name="pduoutlet_sync",
    ),
    path(
        "outlets/<int:pk>/power-on/",
        views.PDUOutletPowerOnView.as_view(),
        name="pduoutlet_power_on",
    ),
    path(
        "outlets/<int:pk>/power-off/",
        views.PDUOutletPowerOffView.as_view(),
        name="pduoutlet_power_off",
    ),
    path(
        "outlets/<int:pk>/power-cycle/",
        views.PDUOutletPowerCycleView.as_view(),
        name="pduoutlet_power_cycle",
    ),
    path(
        "outlets/<int:pk>/push-name/",
        views.PDUOutletPushNameView.as_view(),
        name="pduoutlet_push_name",
    ),
    # PDU Inlet
    path(
        "inlets/",
        include(get_model_urls("netbox_pdu_plugin", "pduinlet", detail=False)),
    ),
    path(
        "inlets/<int:pk>/",
        include(get_model_urls("netbox_pdu_plugin", "pduinlet")),
    ),
    path(
        "inlets/<int:pk>/sync/",
        views.PDUInletSyncView.as_view(),
        name="pduinlet_sync",
    ),
    path(
        "inlets/<int:pk>/push-name/",
        views.PDUInletPushNameView.as_view(),
        name="pduinlet_push_name",
    ),
)
