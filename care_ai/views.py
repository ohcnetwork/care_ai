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
    fetch_eka_result,
    get_document_state,
    set_document_state,
    upload_document_v2,
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
        description="Uploads a lab report to eka.care for async parsing. Returns a document_id to poll.",
        request=EkaLabReportInputSerializer,
        responses={
            202: {
                "type": "object",
                "properties": {
                    "document_id": {"type": "string"},
                    "status": {"type": "string"},
                },
            }
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

        try:
            document_id = upload_document_v2(
                file_obj, file_obj.name, file_obj.content_type
            )
        except EkaCareError as e:
            logger.error(e)
            return Response({"detail": str(e)}, status=status.HTTP_502_BAD_GATEWAY)

        set_document_state(document_id, {"status": "processing"})
        return Response(
            {"document_id": document_id, "status": "processing"},
            status=status.HTTP_202_ACCEPTED,
        )


@extend_schema_view(
    get=extend_schema(
        description="Polls the status of a previously uploaded eka.care lab report.",
        responses={
            200: {"type": "object", "properties": {"result": {"type": "array"}}}
        },
    )
)
class EkaLabReportResultView(APIView):
    permission_classes = [
        IsAuthenticated,
        AIPermission,
    ]

    def get(self, request, document_id):
        state = get_document_state(document_id)
        if state is None:
            return Response(
                {"detail": "Unknown or expired document"},
                status=status.HTTP_404_NOT_FOUND,
            )

        if state["status"] == "error":
            return Response(
                {
                    "detail": state.get(
                        "detail", "eka.care failed to process this document"
                    )
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )

        if state["status"] != "completed":
            # eka.care parses async — ask it directly each poll until it's ready.
            try:
                results = fetch_eka_result(document_id)
            except EkaCarePendingError:
                return Response({"status": "processing"}, status=status.HTTP_200_OK)
            except EkaCareError as e:
                logger.error(e)
                set_document_state(document_id, {"status": "error", "detail": str(e)})
                return Response({"detail": str(e)}, status=status.HTTP_502_BAD_GATEWAY)

            state = {"status": "completed", "results": results}
            set_document_state(document_id, state)

        results = [
            {
                "test_name": entry["name"],
                "value": entry.get("value", ""),
                "unit": entry.get("unit"),
                "loinc_code": entry.get("loinc"),
            }
            for entry in state["results"]
        ]
        return Response(
            {"status": "completed", "result": results}, status=status.HTTP_200_OK
        )
