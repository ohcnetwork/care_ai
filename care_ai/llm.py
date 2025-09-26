import time
from base64 import b64encode

import litellm
from django.conf import settings as dj_settings

from .settings import plugin_settings as settings

if dj_settings.DEBUG:
    litellm._turn_on_debug()

system_prompt = settings.CARE_AI_SYSTEM_PROMPT or (
    "You are a helpful AI assistant that provides information in medical context based on user input. "
    "Use the provided text and images to generate accurate and concise responses. "
    "You only have one chance to get it right, so be careful and thorough in your analysis. "
    "Do not hallucinate as this is a critical task."
)

prompt = [
    {
        "role": "system",
        "content": system_prompt,
    },
    {
        "role": "user",
        "content": "Given the following text and images, provide a detailed response",
    },
]


def encode_image(image) -> str:
    return f"data:{image.content_type};base64,{b64encode(image.read()).decode()}"


def ask_ai(model: str, text: str, images: list) -> str:
    message = prompt.copy()

    message.append(
        {
            "role": "user",
            "content": [{"type": "text", "text": text}],
        }
    )
    if images:
        if not litellm.supports_vision(model=model):
            raise ValueError(f"Model {model} does not support image inputs")
        for image in images:
            message[-1]["content"].append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": encode_image(image),
                        "format": image.content_type,
                    },
                }
            )

    start = time.time()
    response = litellm.completion(
        model=model,
        messages=message,
        max_tokens=1000,
    )
    end = time.time()

    usage = {
        "input": response.usage.prompt_tokens,
        "output": response.usage.completion_tokens,
        "seconds": end - start,
    }

    try:
        output = response.choices[0].message.content
    except (KeyError, IndexError):
        raise ValueError("Invalid response from AI model")
    return output, usage
