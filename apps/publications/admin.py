from django.contrib import admin

from .models import Publication, PublicationAuthor


class PublicationAuthorInline(admin.TabularInline):
    model = PublicationAuthor
    extra = 1
    autocomplete_fields = ['teacher', 'student', 'adjunct']


@admin.register(Publication)
class PublicationAdmin(admin.ModelAdmin):
    list_display = ['title', 'kind', 'year', 'source', 'vak', 'rinc', 'scopus', 'wos', 'quartile']
    list_filter = ['kind', 'year', 'vak', 'rinc', 'rinc_core', 'scopus', 'wos', 'quartile']
    search_fields = ['title', 'source', 'doi']
    autocomplete_fields = ['project']
    inlines = [PublicationAuthorInline]
