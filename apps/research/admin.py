from django.contrib import admin

from .models import Participant, ResearchProject


class StartYearFilter(admin.SimpleListFilter):
    title = 'год начала'
    parameter_name = 'start_year'

    def lookups(self, request, model_admin):
        years = ResearchProject.objects.dates('start_date', 'year', order='DESC')
        return [(str(d.year), str(d.year)) for d in years]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(start_date__year=self.value())
        return queryset


class ParticipantInline(admin.TabularInline):
    model = Participant
    extra = 1
    autocomplete_fields = ['teacher']


@admin.register(ResearchProject)
class ResearchProjectAdmin(admin.ModelAdmin):
    list_display = ['title', 'start_date', 'end_date', 'status']
    list_filter = ['status', StartYearFilter]
    search_fields = ['title']
    date_hierarchy = 'start_date'
    inlines = [ParticipantInline]
