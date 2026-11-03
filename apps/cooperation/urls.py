from django.urls import path

from . import views

app_name = 'cooperation'

urlpatterns = [
    path('', views.CooperationContractListView.as_view(), name='contract_list'),
    path('add/', views.CooperationContractCreateView.as_view(), name='contract_create'),
    path('<int:pk>/', views.CooperationContractDetailView.as_view(), name='contract_detail'),
    path('<int:pk>/edit/', views.CooperationContractUpdateView.as_view(), name='contract_update'),
    path('<int:pk>/delete/', views.CooperationContractDeleteView.as_view(), name='contract_delete'),
]
