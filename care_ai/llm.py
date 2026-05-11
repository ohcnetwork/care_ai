import time
from base64 import b64encode

import litellm
from litellm.utils import supports_pdf_input
from django.conf import settings as dj_settings

from .settings import plugin_settings as settings

if dj_settings.DEBUG:
    litellm._turn_on_debug()


def encode_image(image) -> str:
    return f"data:{image.content_type};base64,{b64encode(image.read()).decode()}"

def encode_pdf(pdf) -> str:
    return f"data:application/pdf;base64,{b64encode(pdf.read()).decode()}"

def ask_ai(model: str, text: str, images: list, pdfs: list, custom_prompt: str = None) -> str:
    # Combine custom prompt with text if provided
    if custom_prompt:
        user_text = f"{custom_prompt}\n\n{text}" if text else custom_prompt
    else:
        user_text = text
    
    message = [
        {
            "role": "user",
            "content": [{"type": "text", "text": user_text}],
        }
    ]
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
    
    if pdfs:
        if not supports_pdf_input(model, None):
            raise ValueError(f"Model {model} does not support document inputs")
        for pdf in pdfs:
            message[-1]["content"].append(
                {
                    "type": "file",
                    "file": {
                        "file_data": encode_pdf(pdf),
                    },
                }
            )

    start = time.time()
    response = litellm.completion(
        model=model,
        messages=message,
        **{settings.CARE_AI_MAX_TOKENS_PARAM_NAME: settings.CARE_AI_MAX_TOKENS},
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
