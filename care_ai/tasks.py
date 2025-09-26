from celery import current_app, shared_task
from celery.schedules import crontab
from django.utils.timezone import now

from .models import UserAiUsageStats


@shared_task
def reset_ai_usage_limits():
    UserAiUsageStats.objects.update(
        total_input_tokens=0,
        total_output_tokens=0,
        total_usage_seconds=0,
        resets_at=now(),
    )


@current_app.on_after_finalize.connect
def setup_periodic_tasks(sender, **kwargs):
    sender.add_periodic_task(
        crontab(hour="0", minute="0"),
        reset_ai_usage_limits.s(),
        name="reset_ai_usage_limits",
    )
