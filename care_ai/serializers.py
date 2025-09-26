from rest_framework import serializers

from .settings import plugin_settings as settings

max_image_size_bytes = settings.CARE_AI_MAX_IMAGE_SIZE_MB * 1024 * 1024


class ContentInputSerializer(serializers.Serializer):
    text = serializers.CharField(required=False, allow_blank=True)
    images = serializers.ListField(
        child=serializers.ImageField(), required=False, allow_empty=True
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

    def validate(self, attrs):
        if not attrs.get("text") and not attrs.get("images"):
            raise serializers.ValidationError(
                "At least one of 'text' or 'images' must be provided."
            )
        return attrs

    class Meta:
        fields = ["text", "images"]
