from . import views
from django.urls import path

urlpatterns = [
    path("index/",views.ClientesListView.as_view(),name="index"),
    path("detallepagos/<int:pk>/",views.PagosListView.as_view(),name="detallePagos"),
    path("paymentRegister/",views.PagoNuevoListView.as_view(),name="paymentRegister"),
    path("cortesRegister/",views.CortesView.as_view(),name="cortesRegister"),
    path("ips-disponibles/",views.IpsAvaibleView.as_view(),name='ips-disponibles' ),
    path("activarServicio/",views.ActivarServicio.as_view(),name='activarServicio' ),
    path("antenaData/<int:pk>/",views.AntenaView.as_view(),name='antenaData'),
    path("antenaReboot/<int:pk>/",views.RebootAntenaView.as_view(),name="rebootAntena"),
    path("sectorReboot/<int:pk>/",views.RebootSectorView.as_view(),name="rebootAntena"),
    path("sectorData/<int:pk>/",views.SectorView.as_view(),name='sectorData'),
    path("cortarServicio/",views.CortarServicio.as_view(),name='cortarServicio' ),
    path("antenaMikrotikData/<int:pk>/",views.MikrotikStatusView.as_view(),name='antenaMikrotikData'),
    path("lastPayment/<int:pk>/",views.LastPayment.as_view(),name='ultimoPago'),
    path("editInfoAntena/<int:pk>/",views.EditAntenaView.as_view(),name="EditarAntena"),
    path("sector/<int:pk>/tx-health/",views.SectorTxHealthView.as_view(), name ="AutoReboot"),
    path("tokenExpoObtain/",views.tokenObteinView.as_view(), name ="AutoReboot"),

    path("airos/toggle-lan/<int:pk>/",views.ToggleAirosLanAPIView.as_view(),name="airos_toggle_lan"),
]
