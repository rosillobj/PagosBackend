from rest_framework.routers import DefaultRouter
from .views import PendienteViewSet

router = DefaultRouter()
router.register(r'pendientes', PendienteViewSet, basename='pendientes')

urlpatterns = router.urls