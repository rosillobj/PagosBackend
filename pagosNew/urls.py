from django.contrib import admin
from django.urls import path,include
from django.conf import settings
from django.conf.urls.static import static
from login import views
from rest_framework_simplejwt.views import TokenObtainPairView,TokenRefreshView


urlpatterns = [
    path('admin/', admin.site.urls),
    path("login/token/", TokenObtainPairView.as_view(),name = "get_token"),
    path("login/token/refresh/", TokenRefreshView.as_view(), name = "refresh"),
    path("login-auth/", include("rest_framework.urls")),
    path('loginRegister/',views.UserRegister.as_view(),name='loginRegister'),
    path('pagos/',include("pagos.urls")),
    path("borrego/",include("borrego.urls")),
]
