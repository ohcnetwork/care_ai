import logging

from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import parsers, status
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from care.emr.models.patient import Patient
from care.security.authorization import AuthorizationController
from care.users.models import UserFlag
from care.utils.shortcuts import get_object_or_404

from .constants import FLAG_CONFIG_NAME
from .eka import (
    EkaCareError,
    EkaCarePendingError,
    create_eka_document,
    poll_eka_result,
    upload_to_presigned_url,
)
from .llm import ask_ai
from .models import UserAiUsageStats
from .serializers import ContentInputSerializer, EkaLabReportInputSerializer
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

    extend_schema(
        description="Endpoint to interact with the AI model. Accepts text and optional images, returns AI-generated response.",
        request=ContentInputSerializer,
        responses={
            200: {"type": "object", "properties": {"result": {"type": "string"}}}
        },
    )

    def post(self, request):
        serializer = ContentInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        model = data.get("model") or settings.CARE_AI_DEFAULT_MODEL
        text = data.get("text")
        prompt = data.get("prompt")
        images = data.get("images")
        pdfs = data.get("pdfs")

        usage, _ = UserAiUsageStats.objects.get_or_create(user=request.user)

        if usage.total_tokens() >= settings.CARE_AI_MAX_TOKENS_PER_USER:
            return Response(
                {"detail": "Token limit exceeded"},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        try:
            ai_output, tokens_used = ask_ai(model, text, images, pdfs, prompt)
            usage.update_stats(
                input_tokens=tokens_used["input"],
                output_tokens=tokens_used["output"],
                usage_seconds=tokens_used["seconds"],
            )
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(e)
            return Response(
                {"detail": "AI processing failed"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response({"result": ai_output}, status=status.HTTP_200_OK)


@extend_schema_view(
    post=extend_schema(
        description="Parses a lab report via eka.care and returns structured vitals.",
        request=EkaLabReportInputSerializer,
        responses={
            200: {"type": "object", "properties": {"result": {"type": "array"}}}
        },
    )
)
class EkaLabReportView(APIView):
    parser_classes = [parsers.MultiPartParser]
    permission_classes = [
        IsAuthenticated,
        AIPermission,
    ]

    def post(self, request):
        serializer = EkaLabReportInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        file_obj = data["file"]

        patient_obj = get_object_or_404(Patient, external_id=data["patient"])
        if not AuthorizationController.call(
            "can_view_clinical_data", request.user, patient_obj
        ):
            return Response(
                {
                    "detail": "You do not have permission to access this patient's records"
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        if not settings.CARE_AI_EKA_API_KEY:
            return Response(
                {"detail": "eka.care integration is not configured"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        # TODO: eka.care requires a pre-registered patient OID, not CARE's external_id.
        # Hardcoded until patient provisioning on eka.care is figured out.
        patient_id = "178759304785317"
        try:
            document_id, form_url, form_fields = create_eka_document(
                patient_id, file_obj.content_type, file_obj.size
            )
            upload_to_presigned_url(
                form_url, form_fields, file_obj, file_obj.name, file_obj.content_type
            )
            smart_report = poll_eka_result(
                document_id,
                patient_id,
                settings.CARE_AI_EKA_POLL_TIMEOUT_SECONDS,
                settings.CARE_AI_EKA_POLL_INTERVAL_SECONDS,
            )
        except EkaCarePendingError as e:
            return Response({"detail": str(e)}, status=status.HTTP_504_GATEWAY_TIMEOUT)
        except EkaCareError as e:
            logger.error(e)
            return Response({"detail": str(e)}, status=status.HTTP_502_BAD_GATEWAY)

        results = [
            {
                "test_name": entry["name"],
                "value": entry.get("value", ""),
                "unit": entry.get("unit"),
            }
            for entry in smart_report.get("verified", [])
        ]
        return Response({"result": results}, status=status.HTTP_200_OK)
