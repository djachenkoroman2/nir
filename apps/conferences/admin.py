from django.contrib import admin

from .models import Conference, Report, ReportSpeaker


class ReportInline(admin.TabularInline):
    model = Report
    fields = ['title', 'form']
    extra = 0
    show_change_link = True


@admin.register(Conference)
class ConferenceAdmin(admin.ModelAdmin):
    list_display = ['title', 'level', 'location', 'start_date', 'end_date']
    list_filter = ['level']
    search_fields = ['title', 'location']
    date_hierarchy = 'start_date'
    inlines = [ReportInline]


class ReportSpeakerInline(admin.TabularInline):
    model = ReportSpeaker
    extra = 1
    autocomplete_fields = ['teacher', 'student']


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ['title', 'conference', 'form']
    list_filter = ['form', 'conference__level']
    search_fields = ['title', 'conference__title']
    autocomplete_fields = ['conference', 'publication']
    inlines = [ReportSpeakerInline]
