from django.contrib import admin

from .models import Adjunct, AdjunctAchievement, PlanStage, Task, TaskComment


class PlanStageInline(admin.TabularInline):
    model = PlanStage
    fields = ['study_year', 'kind', 'title', 'due_date', 'status', 'completed_date']
    extra = 0


@admin.register(Adjunct)
class AdjunctAdmin(admin.ModelAdmin):
    list_display = ['full_name', 'admission_year', 'study_form', 'supervisor', 'status']
    list_filter = ['status', 'supervisor', 'admission_year', 'study_form']
    search_fields = ['last_name', 'first_name', 'middle_name', 'dissertation_topic']
    autocomplete_fields = ['supervisor', 'user']
    inlines = [PlanStageInline]

    @admin.display(description='ФИО', ordering='last_name')
    def full_name(self, obj):
        return obj.full_name


class TaskCommentInline(admin.TabularInline):
    model = TaskComment
    fields = ['author', 'text', 'created_at', 'is_system']
    readonly_fields = ['created_at']
    extra = 0


class AssigneeKindFilter(admin.SimpleListFilter):
    title = 'исполнитель'
    parameter_name = 'assignee'

    def lookups(self, request, model_admin):
        return [('adjunct', 'адъюнкт'), ('student', 'курсант')]

    def queryset(self, request, queryset):
        if self.value() in ('adjunct', 'student'):
            return queryset.filter(**{f'{self.value()}__isnull': False})
        return queryset


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ['title', 'person', 'status', 'priority', 'due_date']
    list_select_related = ['adjunct', 'student']
    list_filter = [AssigneeKindFilter, 'status', 'priority', 'adjunct']
    search_fields = ['title', 'description', 'adjunct__last_name', 'student__last_name']
    autocomplete_fields = ['adjunct', 'student', 'created_by']
    inlines = [TaskCommentInline]

    @admin.display(description='исполнитель')
    def person(self, task):
        return task.person


@admin.register(AdjunctAchievement)
class AdjunctAchievementAdmin(admin.ModelAdmin):
    list_display = ['title', 'adjunct', 'kind', 'level', 'result', 'date']
    list_filter = ['kind', 'level']
    search_fields = ['title', 'result', 'adjunct__last_name']
    autocomplete_fields = ['adjunct']
