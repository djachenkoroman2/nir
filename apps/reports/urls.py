from django.urls import path

from . import views

app_name = 'reports'

urlpatterns = [
    path('', views.ReportListView.as_view(), name='report_list'),
    path('form16/', views.form16_own, name='form16_own'),
    path('form16/<str:kind>/<int:pk>/', views.form16, name='form16'),
    path('work/', views.WorkReportView.as_view(), name='work_own'),
    path('work/<str:kind>/<int:pk>/', views.WorkReportView.as_view(), name='work'),
    # Отчёты на людей одного вида: вид в адресе не нужен, но передаётся представлению и белым спискам кабинета.
    path('plan/', views.PlanReportView.as_view(), name='plan_own'),
    path('plan/<int:pk>/', views.PlanReportView.as_view(), {'kind': 'adjunct'}, name='plan'),
    path('supervision/', views.SupervisionReportView.as_view(), name='supervision_own'),
    path('supervision/<int:pk>/', views.SupervisionReportView.as_view(), {'kind': 'teacher'}, name='supervision'),
    path('cooperation/', views.CooperationReportView.as_view(), name='cooperation'),
    path('department/', views.DepartmentReportView.as_view(), name='department'),
    path('card/<str:kind>/<int:pk>/', views.PersonCardView.as_view(), name='card'),
    path('account/', views.AccountCardView.as_view(), name='account'),
    path('account/<int:pk>/', views.AccountCardView.as_view(), name='account_user'),
    path('activity/', views.ActivityReportView.as_view(), name='activity'),
    path('activity/user/<int:pk>/', views.UserActivityView.as_view(), name='activity_user'),
    path('activity/name/<str:username>/', views.UserActivityView.as_view(), name='activity_name'),
]
