from django.urls import path

from . import views

app_name = 'help'

urlpatterns = [
    path('', views.IndexView.as_view(), name='index'),
    path('<slug:role>/', views.GuideView.as_view(), name='guide'),
    path('<slug:role>/pdf/', views.PdfView.as_view(), name='pdf'),
    path('<slug:role>/<slug:chapter>/', views.ChapterView.as_view(), name='chapter'),
]
