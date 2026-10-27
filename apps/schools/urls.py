from django.urls import path

from . import views

app_name = 'schools'

urlpatterns = [
    path('', views.SchoolListView.as_view(), name='school_list'),
    path('add/', views.SchoolCreateView.as_view(), name='school_create'),
    path('<int:pk>/', views.SchoolDetailView.as_view(), name='school_detail'),
    path('<int:pk>/edit/', views.SchoolUpdateView.as_view(), name='school_update'),
    path('<int:pk>/delete/', views.SchoolDeleteView.as_view(), name='school_delete'),
    path('<int:school_pk>/defenses/add/', views.DefenseCreateView.as_view(), name='defense_create'),
    path('defenses/<int:pk>/edit/', views.DefenseUpdateView.as_view(), name='defense_update'),
    path('defenses/<int:pk>/delete/', views.DefenseDeleteView.as_view(), name='defense_delete'),
]
