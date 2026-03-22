from netbox.api.routers import NetBoxRouter

from . import views

app_name = 'netbox_pdu_plugin'

router = NetBoxRouter()
router.register('managed-pdus', views.ManagedPDUViewSet)
router.register('outlets', views.PDUOutletViewSet)
router.register('inlets', views.PDUInletViewSet)

urlpatterns = router.urls
