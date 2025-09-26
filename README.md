# Care Ai

[![Release Status](https://img.shields.io/pypi/v/care_ai.svg)](https://pypi.python.org/pypi/care_ai)
[![Build Status](https://github.com/ohcnetwork/care_ai/actions/workflows/build.yaml/badge.svg)](https://github.com/ohcnetwork/care_ai/actions/workflows/build.yaml)

Care Ai is a plugin for care to add ai completion for text and image inputs.


## Features

- Text and image input support
- Support for multiple AI providers (OpenAI, Azure OpenAI, etc.)

## Installation

https://care-be-docs.ohc.network/development/pluggable-apps.html

https://github.com/ohcnetwork/care/blob/develop/plug_config.py


To install care ai, you can add the plugin config in [care/plug_config.py](https://github.com/ohcnetwork/care/blob/develop/plug_config.py) as follows:

```python
...

ai_plug = Plug(
    name="care_ai",
    package_name="git+https://github.com/ohcnetwork/care_ai.git",
    version="@main",
    configs={
        "CARE_AI_MAX_IMAGES" : 5,
        "CARE_AI_MAX_IMAGE_SIZE_MB" : 2,
        "CARE_AI_MAX_TOKENS_PER_USER" : 10000,
        "CARE_AI_MODEL" : "github/gpt-4o",
    },
)
plugs = [ai_plug]
...
```

the api key of the api provider needs to added to the environment eg.


The plugin will try to find the API key from the config first and then from the environment variable.

## License

This project is licensed under the terms of the [MIT license](LICENSE).


---
This plugin was created with [Cookiecutter](https://github.com/audreyr/cookiecutter) using the [ohcnetwork/care-plugin-cookiecutter](https://github.com/ohcnetwork/care-plugin-cookiecutter).
