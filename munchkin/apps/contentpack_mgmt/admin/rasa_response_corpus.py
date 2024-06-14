from django.contrib import admin
from unfold.admin import ModelAdmin

from apps.contentpack_mgmt.models import RasaResponseCorpus
from apps.core.admin.guarded_admin_base import GuardedAdminBase


@admin.register(RasaResponseCorpus)
class RasaResponseCorpusAdmin(GuardedAdminBase):
    list_display = ['response', 'corpus']
    search_fields = ['corpus']
    list_filter = ['response']
    list_display_links = ['corpus']
    ordering = ['id']
    filter_horizontal = []
