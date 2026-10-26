from django.urls import path

from . import views

app_name = 'research'

urlpatterns = [
    path('', views.ResearchProjectListView.as_view(), name='project_list'),
    path('add/', views.ResearchProjectCreateView.as_view(), name='project_create'),
    path('<int:pk>/', views.ResearchProjectDetailView.as_view(), name='project_detail'),
    path('<int:pk>/edit/', views.ResearchProjectUpdateView.as_view(), name='project_update'),
    path('<int:pk>/delete/', views.ResearchProjectDeleteView.as_view(), name='project_delete'),
]
