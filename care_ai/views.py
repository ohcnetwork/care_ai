import logging

from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import parsers, status
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from care.users.models import UserFlag

from .constants import FLAG_CONFIG_NAME
from .llm import ask_ai
from .models import UserAiUsageStats
from .serializers import ContentInputSerializer
from .settings import plugin_settings as settings

logger = logging.getLogger(__name__)


class AIPermission(BasePermission):
    def has_permission(self, request, view):
        if request.user.is_superuser:
            return True
        return UserFlag.check_user_has_flag(request.user.id, FLAG_CONFIG_NAME)


@extend_schema_view(
    post=extend_schema(
        description="Endpoint to interact with the AI model. Accepts text and optional images, returns AI-generated response.",
        request=ContentInputSerializer,
        responses={
            200: {"type": "object", "properties": {"result": {"type": "string"}}}
        },
    )
)
class AskAIView(APIView):
    parser_classes = [parsers.MultiPartParser]
    permission_classes = [
        IsAuthenticated,
        AIPermission,
    ]

    # ContentInputSerializer
    extend_schema(
        description="Endpoint to interact with the AI model. Accepts text and optional images, returns AI-generated response.",
        request=ContentInputSerializer,
        responses={
            200: {"type": "object", "properties": {"result": {"type": "string"}}}
        },
    )

    def post(self, request):
        print(request.data)
        serializer = ContentInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        model = data.get("model") or settings.CARE_AI_DEFAULT_MODEL
        text = data.get("text")
        images = data.get("images")

        usage, _ = UserAiUsageStats.objects.get_or_create(user=request.user)

        if usage.total_tokens() >= settings.CARE_AI_MAX_TOKENS_PER_USER:
            return Response(
                {"detail": "Token limit exceeded"},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        try:
            ai_output, tokens_used = ask_ai(model, text, images)
            usage.update_stats(
                input_tokens=tokens_used["input"],
                output_tokens=tokens_used["output"],
                usage_seconds=tokens_used["seconds"],
            )
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.debug(e)
            return Response(
                {"detail": "AI processing failed"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response({"result": ai_output}, status=status.HTTP_200_OK)
