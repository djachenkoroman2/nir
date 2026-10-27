from django.urls import path

from . import views

app_name = 'tasks'

urlpatterns = [
    path('', views.MyTaskListView.as_view(), name='my_tasks'),
    path('<int:pk>/', views.TaskDetailView.as_view(), name='task_detail'),
    path('<int:pk>/edit/', views.TaskUpdateView.as_view(), name='task_update'),
    path('<int:pk>/delete/', views.TaskDeleteView.as_view(), name='task_delete'),
    path('<int:pk>/status/', views.TaskStatusView.as_view(), name='task_status'),
    path('comments/<int:pk>/delete/', views.TaskCommentDeleteView.as_view(), name='comment_delete'),
]
