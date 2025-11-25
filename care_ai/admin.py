from django.contrib import admin

from care_ai.models import UserAiUsageStats, UserAiUsage

admin.site.register(UserAiUsage)
admin.site.register(UserAiUsageStats)
