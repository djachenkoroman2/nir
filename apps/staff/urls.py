from django.urls import path

from . import views

app_name = 'staff'

urlpatterns = [
    path('', views.TeacherListView.as_view(), name='teacher_list'),
    path('add/', views.TeacherCreateView.as_view(), name='teacher_create'),
    path('<int:pk>/', views.TeacherDetailView.as_view(), name='teacher_detail'),
    path('<int:pk>/edit/', views.TeacherUpdateView.as_view(), name='teacher_update'),
    path('<int:pk>/delete/', views.TeacherDeleteView.as_view(), name='teacher_delete'),
]
