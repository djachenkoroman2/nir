from django.urls import path

from . import views

app_name = 'ip'

urlpatterns = [
    path('', views.IntellectualPropertyListView.as_view(), name='ip_list'),
    path('add/', views.IntellectualPropertyCreateView.as_view(), name='ip_create'),
    path('<int:pk>/', views.IntellectualPropertyDetailView.as_view(), name='ip_detail'),
    path('<int:pk>/edit/', views.IntellectualPropertyUpdateView.as_view(), name='ip_update'),
    path('<int:pk>/delete/', views.IntellectualPropertyDeleteView.as_view(), name='ip_delete'),
]
