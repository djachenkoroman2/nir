from django.contrib import admin

from .models import DissertationDefense, ScientificSchool


class DefenseYearFilter(admin.SimpleListFilter):
    title = 'год защиты'
    parameter_name = 'defense_year'

    def lookups(self, request, model_admin):
        years = DissertationDefense.objects.dates('defense_date', 'year', order='DESC')
        return [(str(d.year), str(d.year)) for d in years]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(defense_date__year=self.value())
        return queryset


class DissertationDefenseInline(admin.TabularInline):
    model = DissertationDefense
    fields = ['full_name', 'kind', 'title', 'defense_date']
    extra = 0
    show_change_link = True


@admin.register(ScientificSchool)
class ScientificSchoolAdmin(admin.ModelAdmin):
    list_display = ['name', 'is_active']
    list_filter = ['is_active']
    search_fields = ['name']
    filter_horizontal = ['leaders']
    inlines = [DissertationDefenseInline]


@admin.register(DissertationDefense)
class DissertationDefenseAdmin(admin.ModelAdmin):
    list_display = ['full_name', 'kind', 'defense_date', 'school', 'supervisor']
    list_filter = ['kind', 'school', DefenseYearFilter]
    search_fields = ['full_name', 'title']
    autocomplete_fields = ['teacher', 'adjunct', 'supervisor']
