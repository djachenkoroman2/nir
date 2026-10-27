from django.urls import path

from . import views

app_name = 'adjuncts'

urlpatterns = [
    path('', views.AdjunctListView.as_view(), name='adjunct_list'),
    path('add/', views.AdjunctCreateView.as_view(), name='adjunct_create'),
    path('<int:pk>/', views.AdjunctDetailView.as_view(), name='adjunct_detail'),
    path('<int:pk>/edit/', views.AdjunctUpdateView.as_view(), name='adjunct_update'),
    path('<int:pk>/contacts/', views.AdjunctContactsView.as_view(), name='adjunct_contacts'),
    path('<int:pk>/delete/', views.AdjunctDeleteView.as_view(), name='adjunct_delete'),
    path('<int:adjunct_pk>/plan/add/', views.PlanStageCreateView.as_view(), name='stage_create'),
    path('plan/<int:pk>/edit/', views.PlanStageUpdateView.as_view(), name='stage_update'),
    path('plan/<int:pk>/delete/', views.PlanStageDeleteView.as_view(), name='stage_delete'),
    path('plan/<int:pk>/start/', views.PlanStageStartView.as_view(), name='stage_start'),
    path('<int:adjunct_pk>/achievements/add/', views.AchievementCreateView.as_view(), name='achievement_create'),
    path('achievements/<int:pk>/edit/', views.AchievementUpdateView.as_view(), name='achievement_update'),
    path('achievements/<int:pk>/delete/', views.AchievementDeleteView.as_view(), name='achievement_delete'),
    path('<int:adjunct_pk>/tasks/', views.AdjunctTaskListView.as_view(), name='adjunct_tasks'),
    path('<int:adjunct_pk>/tasks/add/', views.AdjunctTaskCreateView.as_view(), name='task_create'),
]
