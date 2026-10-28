from django.urls import path

from . import views

app_name = 'conferences'

urlpatterns = [
    path('', views.ConferenceListView.as_view(), name='conference_list'),
    path('add/', views.ConferenceCreateView.as_view(), name='conference_create'),
    path('<int:pk>/', views.ConferenceDetailView.as_view(), name='conference_detail'),
    path('<int:pk>/edit/', views.ConferenceUpdateView.as_view(), name='conference_update'),
    path('<int:pk>/delete/', views.ConferenceDeleteView.as_view(), name='conference_delete'),
    path('reports/add/', views.ReportConferenceChoiceView.as_view(), name='report_choose'),
    path('<int:conference_pk>/reports/add/', views.ReportCreateView.as_view(), name='report_create'),
    path('reports/<int:pk>/edit/', views.ReportUpdateView.as_view(), name='report_update'),
    path('reports/<int:pk>/delete/', views.ReportDeleteView.as_view(), name='report_delete'),
]
