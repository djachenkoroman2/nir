from django.urls import path

from . import views

app_name = 'reports'

urlpatterns = [
    path('', views.ReportListView.as_view(), name='report_list'),
    path('form16/', views.form16_own, name='form16_own'),
    path('form16/<str:kind>/<int:pk>/', views.form16, name='form16'),
]
