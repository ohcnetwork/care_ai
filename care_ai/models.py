from django.contrib.auth import get_user_model
from django.db import models
from django.utils.timezone import now

User = get_user_model()


class UserAiUsage(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    input_tokens = models.IntegerField(default=0)
    output_tokens = models.IntegerField(default=0)
    usage_seconds = models.IntegerField(default=0)

    def total_tokens(self):
        return self.input_tokens + self.output_tokens


class UserAiUsageStats(models.Model):
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="ai_usage_stats"
    )
    total_input_tokens = models.BigIntegerField(default=0)
    total_output_tokens = models.BigIntegerField(default=0)
    total_usage_seconds = models.BigIntegerField(default=0)
    resets_at = models.DateTimeField(default=now)

    def update_stats(self, input_tokens, output_tokens, usage_seconds):
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens
        self.total_usage_seconds += usage_seconds
        UserAiUsage.objects.create(
            user=self.user,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            usage_seconds=usage_seconds,
        )
        self.save()

    def total_tokens(self):
        return self.total_input_tokens + self.total_output_tokens
