from django.contrib import admin

from .models import IntellectualProperty, IntellectualPropertyAuthor


class IntellectualPropertyAuthorInline(admin.TabularInline):
    model = IntellectualPropertyAuthor
    extra = 1
    autocomplete_fields = ['teacher', 'student']


@admin.register(IntellectualProperty)
class IntellectualPropertyAdmin(admin.ModelAdmin):
    list_display = ['title', 'kind', 'number', 'registration_date', 'holder']
    list_filter = ['kind']
    search_fields = ['title', 'number', 'holder']
    date_hierarchy = 'registration_date'
    autocomplete_fields = ['project']
    inlines = [IntellectualPropertyAuthorInline]
