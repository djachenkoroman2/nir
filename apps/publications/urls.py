from django.urls import path

from . import views

app_name = 'publications'

urlpatterns = [
    path('', views.PublicationListView.as_view(), name='publication_list'),
    path('add/', views.PublicationCreateView.as_view(), name='publication_create'),
    path('<int:pk>/', views.PublicationDetailView.as_view(), name='publication_detail'),
    path('<int:pk>/edit/', views.PublicationUpdateView.as_view(), name='publication_update'),
    path('<int:pk>/delete/', views.PublicationDeleteView.as_view(), name='publication_delete'),
]
