from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

admin.site.site_header = 'Учёт показателей НИР кафедры'
admin.site.site_title = 'НИР кафедры'

urlpatterns = [
    path('admin/', admin.site.urls),
    path('login/', auth_views.LoginView.as_view(redirect_authenticated_user=True), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('teachers/', include('apps.staff.urls')),
    path('research/', include('apps.research.urls')),
    path('publications/', include('apps.publications.urls')),
    path('ip/', include('apps.ip.urls')),
    path('conferences/', include('apps.conferences.urls')),
    path('', include('apps.core.urls')),
]
