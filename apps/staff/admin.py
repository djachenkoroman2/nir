from django.contrib import admin

from .models import Teacher


@admin.register(Teacher)
class TeacherAdmin(admin.ModelAdmin):
    list_display = ['full_name', 'position', 'degree', 'academic_title', 'is_active']
    list_filter = ['position', 'degree', 'academic_title', 'is_active']
    search_fields = ['last_name', 'first_name', 'middle_name']
    autocomplete_fields = ['user']

    @admin.display(description='ФИО', ordering='last_name')
    def full_name(self, obj):
        return obj.full_name
