"""Azure Blob + AI Vision for phone-as-sensor stills. Managed identity in Azure."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from app.config import get_settings
from app.models.event import EventType, Severity

log = logging.getLogger("urbansense.azure")

_TAG_TO_TYPE: list[tuple[tuple[str, ...], EventType, Severity]] = [
    (("pothole", "pot-hole", "hole in the road"), EventType.POTHOLE, Severity.HIGH),
    (("crack", "cracked", "damaged road", "road damage"), EventType.ROAD_DAMAGE, Severity.MEDIUM),
    (("flood", "flooded", "waterlogging", "standing water", "puddle"), EventType.WATERLOGGING, Severity.HIGH),
    (("traffic jam", "congestion", "traffic"), EventType.TRAFFIC_CONGESTION, Severity.MEDIUM),
    (("pedestrian", "person", "people"), EventType.PEDESTRIAN, Severity.LOW),
    (("car", "truck", "bus", "vehicle", "motorcycle"), EventType.VEHICLE, Severity.LOW),
]


MAX_STILL_BYTES = 3_500_000


class StillRejected(ValueError):
    pass


def azure_stack_status() -> dict:
    settings = get_settings()
    return {
        "vision": azure_vision_status(),
        "blob": {"configured": bool(settings.azure_storage_account_url.strip())},
        "openai": azure_openai_status(),
        "content_safety": azure_safety_status(),
    }


def azure_openai_status() -> dict:
    settings = get_settings()
    on = bool(settings.azure_openai_endpoint.strip())
    return {
        "ai_status": "REAL" if on else "DISABLED",
        "provider": "Azure OpenAI",
        "model": settings.azure_openai_deployment or "gpt-4o-mini",
        "note": "ICCC officer brief from stored facts only. Not a detector.",
        "configured": on,
    }


def azure_safety_status() -> dict:
    settings = get_settings()
    on = bool(settings.azure_contentsafety_endpoint.strip())
    return {
        "ai_status": "REAL" if on else "DISABLED",
        "provider": "Azure AI Content Safety",
        "note": "Blocks high-severity stills before ingest.",
        "configured": on,
    }


def validate_still(data: bytes) -> None:
    settings = get_settings()
    limit = settings.still_max_bytes or MAX_STILL_BYTES
    if not data:
        raise StillRejected("empty still")
    if len(data) > limit:
        raise StillRejected("still too large")
    if data[:2] == b"\xff\xd8":
        return
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return
    raise StillRejected("still must be JPEG or PNG")


def screen_still(data: bytes) -> dict:
    settings = get_settings()
    endpoint = settings.azure_contentsafety_endpoint.strip()
    if not endpoint:
        return {"ok": True, "ai_status": "DISABLED", "skipped": True}
    from azure.ai.contentsafety import ContentSafetyClient
    from azure.ai.contentsafety.models import AnalyzeImageOptions, ImageData

    client = ContentSafetyClient(endpoint=endpoint, credential=_credential())
    result = client.analyze_image(AnalyzeImageOptions(image=ImageData(content=data)))
    blocked = []
    for cat in result.categories_analysis or []:
        if getattr(cat, "severity", 0) and cat.severity >= 4:
            blocked.append(getattr(cat, "category", "unknown"))
    if blocked:
        return {"ok": False, "ai_status": "REAL", "blocked": blocked}
    return {"ok": True, "ai_status": "REAL", "blocked": []}


def draft_officer_brief(facts: dict) -> dict:
    settings = get_settings()
    endpoint = settings.azure_openai_endpoint.strip()
    deployment = settings.azure_openai_deployment.strip() or "gpt-4o-mini"
    if not endpoint:
        return {"ok": False, "ai_status": "DISABLED", "reason": "AZURE_OPENAI_ENDPOINT not set"}
    from azure.identity import get_bearer_token_provider
    from openai import AzureOpenAI

    token_provider = get_bearer_token_provider(_credential(), "https://cognitiveservices.azure.com/.default")
    client = AzureOpenAI(
        azure_endpoint=endpoint,
        azure_ad_token_provider=token_provider,
        api_version="2024-10-21",
    )
    system = (
        "You draft a 4-sentence ICCC officer brief from the given facts only. "
        "Do not invent detections, plates, names, or waterlogging neural claims. "
        "Say the system assists authorities and does not accuse. "
        "If a field is missing, say it is unknown."
    )
    user = (
        f"public_code={facts.get('public_code')} type={facts.get('event_type')} "
        f"severity={facts.get('severity')} caption={facts.get('caption')} "
        f"tags={facts.get('tags')} fusion={facts.get('fusion_reason')}"
    )
    resp = client.chat.completions.create(
        model=deployment,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        max_tokens=220,
        temperature=0.2,
    )
    text = (resp.choices[0].message.content or "").strip()
    return {
        "ok": True,
        "ai_status": "REAL",
        "provider": "Azure OpenAI",
        "model": deployment,
        "brief": text,
    }


def azure_vision_status() -> dict:
    settings = get_settings()
    on = bool(settings.azure_vision_endpoint.strip())
    return {
        "ai_status": "REAL" if on else "DISABLED",
        "provider": "Azure AI Vision Image Analysis",
        "method": "azure-ai-vision",
        "note": "Cloud still analysis for phone/edge photos. Not a replacement for local RDD YOLO.",
        "configured": on,
    }


def _credential():
    from azure.identity import DefaultAzureCredential

    return DefaultAzureCredential(exclude_interactive_browser_credential=True)


def save_evidence_blob(filename: str, data: bytes) -> str | None:
    settings = get_settings()
    url = settings.azure_storage_account_url.strip()
    if not url or not data:
        return None
    from azure.storage.blob import BlobServiceClient, ContentSettings

    name = f"{datetime.now(timezone.utc).strftime('%Y%m%d')}/{uuid.uuid4().hex}-{filename}"
    client = BlobServiceClient(account_url=url.rstrip("/"), credential=_credential())
    blob = client.get_blob_client(settings.azure_storage_container, name)
    content = ContentSettings(content_type="image/jpeg")
    blob.upload_blob(data, overwrite=True, content_settings=content)
    return blob.url


def analyze_still(data: bytes) -> dict:
    settings = get_settings()
    endpoint = settings.azure_vision_endpoint.strip()
    if not endpoint:
        return {"ok": False, "ai_status": "DISABLED", "reason": "AZURE_VISION_ENDPOINT not set"}
    from azure.ai.vision.imageanalysis import ImageAnalysisClient
    from azure.ai.vision.imageanalysis.models import VisualFeatures

    client = ImageAnalysisClient(endpoint=endpoint, credential=_credential())
    result = client.analyze(
        image_data=data,
        visual_features=[VisualFeatures.CAPTION, VisualFeatures.TAGS, VisualFeatures.OBJECTS],
        gender_neutral_caption=True,
    )
    caption = ""
    caption_confidence = None
    if result.caption:
        caption = result.caption.text or ""
        caption_confidence = getattr(result.caption, "confidence", None)
    tags = [t.name for t in (result.tags or []) if getattr(t, "name", None)]
    objects = [o.tags[0].name if o.tags else "object" for o in (result.objects or [])]
    mapped = _map_event(tags + objects + ([caption] if caption else []))
    return {
        "ok": True,
        "ai_status": "REAL",
        "engine_status": "REAL",
        "provider": "Azure AI Vision",
        "method": "azure-ai-vision",
        "model": "azure-ai-vision-image-analysis",
        "caption": caption,
        "caption_confidence": caption_confidence,
        "tags": tags[:12],
        "objects": objects[:12],
        "mapped_event_type": mapped[0].value if mapped else None,
        "mapped_severity": mapped[1].value if mapped else None,
    }


def _map_event(phrases: list[str]) -> tuple[EventType, Severity] | None:
    blob = " ".join(p.lower() for p in phrases if p)
    for keys, et, sev in _TAG_TO_TYPE:
        if any(k in blob for k in keys):
            return et, sev
    return None
