from rest_framework import serializers

from .settings import plugin_settings as settings

max_image_size_bytes = settings.CARE_AI_MAX_IMAGE_SIZE_MB * 1024 * 1024
max_pdf_size_bytes = settings.CARE_AI_MAX_PDFS * 1024 * 1024

EKA_MAX_PDF_SIZE_BYTES = 25 * 1024 * 1024
EKA_MAX_IMAGE_SIZE_BYTES = 10 * 1024 * 1024
EKA_ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "application/pdf"}

allowed_models = (
    settings.CARE_AI_ALLOWED_MODELS.split(",")
    if settings.CARE_AI_ALLOWED_MODELS
    else [settings.CARE_AI_DEFAULT_MODEL]
)


class ContentInputSerializer(serializers.Serializer):
    model = serializers.ChoiceField(
        choices=[(model, model) for model in allowed_models],
        default=settings.CARE_AI_DEFAULT_MODEL,
    )
    text = serializers.CharField(required=False, allow_blank=True)
    prompt = serializers.CharField(required=False, allow_blank=True)
    images = serializers.ListField(
        child=serializers.ImageField(), required=False, allow_empty=True
    )
    pdfs = serializers.ListField(
        child=serializers.FileField(), required=False, allow_empty=True
    )

    def validate_images(self, value):
        errors = []
        if len(value) > settings.CARE_AI_MAX_IMAGES:
            errors.append(
                f"Number of images exceeds the maximum limit of {settings.CARE_AI_MAX_IMAGES}."
            )

        for image in value:
            if image.size > max_image_size_bytes:
                errors.append(f"Image {image.name} exceeds the maximum size of 2MB.")
        if errors:
            raise serializers.ValidationError(errors)
        return value

    def validate_pdfs(self, value):
        errors = []
        if len(value) > settings.CARE_AI_MAX_PDFS:
            errors.append(
                f"Number of PDFs exceeds the maximum limit of {settings.CARE_AI_MAX_PDFS}."
            )

        for pdf in value:
            if pdf.size > max_pdf_size_bytes:
                errors.append(f"PDF {pdf.name} exceeds the maximum size of 2MB.")
        if errors:
            raise serializers.ValidationError(errors)
        return value

    def validate(self, attrs):
        if not attrs.get("text") and not attrs.get("images") and not attrs.get("pdfs"):
            raise serializers.ValidationError(
                "At least one of 'text', 'images' or 'pdfs' must be provided."
            )
        return attrs

    class Meta:
        fields = ["text", "images", "pdfs", "model", "prompt"]


class EkaLabReportInputSerializer(serializers.Serializer):
    patient = serializers.UUIDField()
    file = serializers.FileField()

    def validate_file(self, value):
        content_type = value.content_type
        if content_type not in EKA_ALLOWED_CONTENT_TYPES:
            raise serializers.ValidationError(
                f"Unsupported file type {content_type}. "
                "Allowed types: image/jpeg, image/png, application/pdf."
            )
        max_size = (
            EKA_MAX_PDF_SIZE_BYTES
            if content_type == "application/pdf"
            else EKA_MAX_IMAGE_SIZE_BYTES
        )
        if value.size > max_size:
            raise serializers.ValidationError(
                f"File exceeds the maximum allowed size of {max_size // (1024 * 1024)}MB."
            )
        return value
