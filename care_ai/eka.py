import time

import requests

from .settings import plugin_settings as settings


class EkaCareError(Exception):
    """Raised when eka.care rejects a request or returns an unexpected response."""


class EkaCarePendingError(EkaCareError):
    """Raised when eka.care has not finished parsing the document within the poll window."""


def _auth_headers(patient_id: str) -> dict:
    return {
        "Authorization": f"Bearer {settings.CARE_AI_EKA_API_KEY}",
        "X-Pt-Id": patient_id,
    }


def create_eka_document(
    patient_id: str, content_type: str, file_size: int, doc_type: str = "lr"
) -> tuple[str, str, dict]:
    """Obtain a presigned upload URL from eka.care.

    Returns (document_id, form_url, form_fields).
    """
    url = f"{settings.CARE_AI_EKA_BASE_URL}/mr/api/v1/docs"
    payload = {
        "batch_request": [
            {
                "dt": doc_type,
                "dd_e": int(time.time()),
                "files": [{"contentType": content_type, "file_size": file_size}],
            }
        ]
    }
    headers = {**_auth_headers(patient_id), "Content-Type": "application/json"}
    response = requests.post(url, json=payload, headers=headers, timeout=30)
    if not response.ok:
        msg = f"eka.care upload authorization failed: {response.status_code} {response.text}"
        raise EkaCareError(msg)

    data = response.json()
    if data.get("error"):
        raise EkaCareError(
            data.get("message") or "eka.care upload authorization failed"
        )

    batch = data["batch_response"][0]
    if batch.get("error_details"):
        msg = batch["error_details"].get("message") or "eka.care rejected the document"
        raise EkaCareError(msg)

    form = batch["forms"][0]
    return batch["document_id"], form["url"], form["fields"]


def upload_to_presigned_url(
    form_url: str, form_fields: dict, file_obj, filename: str, content_type: str
) -> None:
    """Upload the file bytes to eka.care's presigned S3 URL. Expects a 204 on success."""
    file_obj.seek(0)
    response = requests.post(
        form_url,
        data=form_fields,
        # 'file' must be the last field in the multipart form, per eka.care's docs.
        files={"file": (filename, file_obj, content_type)},
        timeout=60,
    )
    if response.status_code != 204:
        msg = f"eka.care file upload failed: {response.status_code} {response.text}"
        raise EkaCareError(msg)


def poll_eka_result(
    document_id: str, patient_id: str, timeout: int, interval: int
) -> dict:
    """Poll eka.care until the smart_report (structured vitals) is available, or timeout."""
    url = f"{settings.CARE_AI_EKA_BASE_URL}/mr/api/v1/docs/{document_id}"
    headers = _auth_headers(patient_id)
    deadline = time.time() + timeout

    while True:
        response = requests.get(url, headers=headers, timeout=30)
        if response.status_code == 404:
            raise EkaCareError("eka.care could not find the requested document")
        if not response.ok:
            msg = (
                f"eka.care result fetch failed: {response.status_code} {response.text}"
            )
            raise EkaCareError(msg)

        data = response.json()
        if data.get("smart_report"):
            return data["smart_report"]

        if time.time() >= deadline:
            raise EkaCarePendingError("eka.care is still processing this document")

        time.sleep(interval)
