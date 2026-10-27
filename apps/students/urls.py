from django.urls import path

from . import views

app_name = 'students'

urlpatterns = [
    path('', views.StudentListView.as_view(), name='student_list'),
    path('add/', views.StudentCreateView.as_view(), name='student_create'),
    path('<int:pk>/', views.StudentDetailView.as_view(), name='student_detail'),
    path('<int:pk>/edit/', views.StudentUpdateView.as_view(), name='student_update'),
    path('<int:pk>/delete/', views.StudentDeleteView.as_view(), name='student_delete'),
    path('<int:student_pk>/achievements/add/', views.AchievementCreateView.as_view(), name='achievement_create'),
    path('achievements/<int:pk>/edit/', views.AchievementUpdateView.as_view(), name='achievement_update'),
    path('achievements/<int:pk>/delete/', views.AchievementDeleteView.as_view(), name='achievement_delete'),
]
