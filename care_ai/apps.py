from django.apps import AppConfig
from care.utils.registries.feature_flag import FlagRegistry, FlagType

from .constants import FLAG_CONFIG_NAME

PLUGIN_NAME = "care_ai"


class CareAiConfig(AppConfig):
    name = PLUGIN_NAME

    def ready(self):
        FlagRegistry.register(FlagType.FACILITY, FLAG_CONFIG_NAME)
        FlagRegistry.register(FlagType.USER, FLAG_CONFIG_NAME)
