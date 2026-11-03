from django.contrib import admin

from .models import CooperationContract


class IndefiniteFilter(admin.SimpleListFilter):
    title = 'срок действия'
    parameter_name = 'indefinite'

    def lookups(self, request, model_admin):
        return [('yes', 'бессрочные'), ('no', 'с датой окончания')]

    def queryset(self, request, queryset):
        if self.value() == 'yes':
            return queryset.filter(end_date__isnull=True)
        if self.value() == 'no':
            return queryset.filter(end_date__isnull=False)
        return queryset


@admin.register(CooperationContract)
class CooperationContractAdmin(admin.ModelAdmin):
    list_display = ['title', 'number', 'organization', 'term', 'state']
    list_filter = [IndefiniteFilter]
    search_fields = ['title', 'number', 'organization', 'subject']
    date_hierarchy = 'start_date'

    @admin.display(description='Срок действия')
    def term(self, obj):
        return obj.term_display

    @admin.display(description='Состояние')
    def state(self, obj):
        return obj.get_state_display()
