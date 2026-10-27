from django.contrib import admin

from .models import Student, StudentAchievement


class AchievementYearFilter(admin.SimpleListFilter):
    title = 'год'
    parameter_name = 'year'

    def lookups(self, request, model_admin):
        years = StudentAchievement.objects.dates('date', 'year', order='DESC')
        return [(str(d.year), str(d.year)) for d in years]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(date__year=self.value())
        return queryset


class StudentAchievementInline(admin.TabularInline):
    model = StudentAchievement
    fields = ['kind', 'level', 'title', 'result', 'date', 'supervisor']
    extra = 0
    autocomplete_fields = ['supervisor']
    show_change_link = True


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ['full_name', 'group', 'course', 'supervisor', 'status']
    list_filter = ['course', 'status', 'supervisor']
    search_fields = ['last_name', 'first_name', 'middle_name', 'group']
    autocomplete_fields = ['supervisor']
    inlines = [StudentAchievementInline]

    @admin.display(description='ФИО', ordering='last_name')
    def full_name(self, obj):
        return obj.full_name


@admin.register(StudentAchievement)
class StudentAchievementAdmin(admin.ModelAdmin):
    list_display = ['title', 'student', 'kind', 'level', 'result', 'date']
    list_filter = ['kind', 'level', AchievementYearFilter]
    search_fields = ['title', 'result', 'student__last_name']
    autocomplete_fields = ['student', 'supervisor']
