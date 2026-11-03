from django.urls import path

from . import views

app_name = 'core'

urlpatterns = [
    path('', views.home, name='home'),
    path('profile/', views.ProfileEditView.as_view(), name='profile_edit'),
]
