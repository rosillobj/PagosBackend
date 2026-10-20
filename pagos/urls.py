from . import views
from .assignment_audit import StartAssignmentAuditView, AssignmentAuditResultView
from .queue_name_sync import QueueNameSyncView, QueueNameSyncResultView
from .ip_scan import StartIpScanView, IpScanResultView
from .traffic import StartTrafficMeasurement, TrafficMeasurementResult
from django.urls import path

urlpatterns = [
    path("auditoria-asignaciones/", StartAssignmentAuditView.as_view(), name="start_assignment_audit"),
    path("auditoria-asignaciones/<str:token>/", AssignmentAuditResultView.as_view(), name="assignment_audit_result"),
    path("mikrotik/sincronizar-nombres/", QueueNameSyncView.as_view(), name="queue_name_sync"),
    path("mikrotik/sincronizar-nombres/<str:token>/", QueueNameSyncResultView.as_view(), name="queue_name_sync_result"),
    path("ips-disponibles/escanear/", StartIpScanView.as_view(), name="start_ip_scan"),
    path("ips-disponibles/escaneos/<str:token>/", IpScanResultView.as_view(), name="ip_scan_result"),
    path("sectorMikrotikData/<int:pk>/", views.MikrotikSectorStatusView.as_view(), name="mikrotik_sector_status"),
    path("clientes/<int:pk>/medir-consumo/", StartTrafficMeasurement.as_view(), name="start_traffic_measurement"),
    path("mediciones/<str:token>/", TrafficMeasurementResult.as_view(), name="traffic_measurement_result"),
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
    path("sectorData2/<int:pk>/",views.MikrotikStatusView2.as_view(),name='sectorData'),
    path("mikrotik/toggle-interface/<int:pk>/",views.MikrotikToggleInterfaceView.as_view(),name="mikrotik_toggle_interface"),
    path("mikrotik/<int:pk>/balance-mode/",views.MikrotikBalanceModeView.as_view(),name="mikrotik_balance_mode"),
    path("airos/toggle-lan/<int:pk>/",views.ToggleAirosLanAPIView.as_view(),name="airos_toggle_lan"),
    path("updateDay/",views.PagosDayUpdate.as_view(),name="Pagos Update"),

]
