import logging

import requests
from django.core.cache import cache

from .settings import plugin_settings as settings

logger = logging.getLogger(__name__)

DOCUMENT_STATE_TTL_SECONDS = 60 * 60


class EkaCareError(Exception):
    """Raised when eka.care rejects a request or returns an unexpected response."""


class EkaCarePendingError(EkaCareError):
    """Raised when eka.care has not finished parsing the document yet."""


def _auth_headers() -> dict:
    return {"Authorization": f"Bearer {settings.CARE_AI_EKA_API_KEY}"}


def _document_cache_key(document_id: str) -> str:
    return f"care_ai:eka:document:{document_id}"


def set_document_state(document_id: str, state: dict) -> None:
    """Cache processing/completed/error state for a document so repeated polls don't re-hit eka.care once it's done."""
    cache.set(
        _document_cache_key(document_id), state, timeout=DOCUMENT_STATE_TTL_SECONDS
    )


def get_document_state(document_id: str) -> dict | None:
    return cache.get(_document_cache_key(document_id))


def upload_document_v2(file_obj, filename: str, content_type: str) -> str:
    """Upload a document to eka.care's v2 smart-parsing endpoint. Returns the document_id."""
    url = f"{settings.CARE_AI_EKA_BASE_URL}/mr/api/v2/docs"
    file_obj.seek(0)
    response = requests.post(
        url,
        params={"task": "smart"},
        headers=_auth_headers(),
        files={"file": (filename, file_obj, content_type)},
        timeout=60,
    )
    if not response.ok:
        msg = f"eka.care document upload failed: {response.status_code} {response.text}"
        raise EkaCareError(msg)

    data = response.json()
    document_id = (
        data.get("document_id") or data.get("transaction_id") or data.get("id")
    )
    if not document_id:
        msg = f"eka.care upload response did not include a document id: {response.text}"
        raise EkaCareError(msg)
    return document_id


def _find_loinc_code(coding_list: list[dict]) -> str | None:
    for coding in coding_list:
        if coding.get("system") == "http://loinc.org":
            return coding.get("code")
    return None


def _extract_observation(resource: dict) -> dict | None:
    """Pull {name, value, unit, loinc} out of a single FHIR Observation resource."""
    code = resource.get("code", {})
    coding_list = code.get("coding") or [{}]
    coding = coding_list[0]
    name = code.get("text") or coding.get("display") or coding.get("code")
    if name is None:
        return None
    quantity = resource.get("valueQuantity") or {}
    value = quantity.get("value")
    if value is None:
        value = resource.get("valueString", "")
    return {
        "name": name,
        "value": str(value),
        "unit": quantity.get("unit"),
        "loinc": _find_loinc_code(coding_list),
    }


def _extract_results(data) -> list[dict]:
    """Normalize eka.care's parsed payload into a flat [{name, value, unit}] list.

    `data.output.data` (once populated) has been observed as a *list*. The confirmed
    real shape is `{"test_name": ..., "loinc_id": ..., "data": {"value": ..., "unit_processed": ...}}`
    per item; a few other shapes (older `smart_report.verified[]`, a FHIR Bundle of
    Observations, a bare Observation, or an already-flat {name, value} result) are
    also handled defensively since eka hasn't published a fixed schema for this payload.
    """
    if isinstance(data, list):
        results = []
        for item in data:
            results.extend(_extract_results(item))
        return results

    if not isinstance(data, dict):
        logger.warning("eka.care result payload had an unrecognized item: %r", data)
        return []

    smart_report = data.get("smart_report")
    if smart_report:
        return [
            {
                "name": entry["name"],
                "value": entry.get("value", ""),
                "unit": entry.get("unit"),
            }
            for entry in smart_report.get("verified", [])
        ]

    if data.get("resourceType") == "Bundle":
        results = []
        for entry in data.get("entry", []):
            resource = entry.get("resource", {})
            if resource.get("resourceType") != "Observation":
                continue
            observation = _extract_observation(resource)
            if observation:
                results.append(observation)
        return results

    if data.get("resourceType") == "Observation":
        observation = _extract_observation(data)
        return [observation] if observation else []

    if "test_name" in data:
        # Confirmed real shape: {"test_name": "WBC", "loinc_id": "...", "data": {"value": 2.77, "unit_processed": "10*3/mm3", ...}}
        value_block = data.get("data") or {}
        return [
            {
                "name": data["test_name"],
                "value": value_block.get("value", ""),
                "unit": value_block.get("unit_processed") or value_block.get("unit"),
                "loinc": data.get("loinc_id"),
            }
        ]

    if "name" in data and "value" in data:
        return [
            {
                "name": data["name"],
                "value": data.get("value", ""),
                "unit": data.get("unit"),
                "loinc": data.get("loinc"),
            }
        ]

    # Unknown/incomplete shape — treat as still processing rather than failing outright,
    # since eka hasn't documented what an in-progress payload looks like.
    logger.warning("eka.care result payload had an unrecognized shape: %s", data)
    return []


def fetch_eka_result(document_id: str) -> list[dict]:
    """Fetch eka.care's parsed result for a document, once, and raise if not ready yet.

    Called on every poll from `EkaLabReportResultView` until it succeeds. The response
    envelope is `{"status": ..., "data": {"output": {"data": ...}}}`, where
    `data.output.data` is null until parsing finishes.
    """
    url = f"{settings.CARE_AI_EKA_BASE_URL}/mr/api/v1/docs/{document_id}/result"
    response = requests.get(url, headers=_auth_headers(), timeout=30)
    if response.status_code == 404:
        raise EkaCareError("eka.care could not find the requested document")
    if not response.ok:
        msg = f"eka.care result lookup failed: {response.status_code} {response.text}"
        raise EkaCareError(msg)

    envelope = response.json()
    last_status = envelope.get("status")
    payload = (envelope.get("data") or {}).get("output", {}).get("data")
    results = _extract_results(payload) if payload else []
    if not results:
        msg = f"eka.care is still processing this document (last status: {last_status})"
        raise EkaCarePendingError(msg)
    return results
