"""Generate image artifacts for the DSL video pipeline via OpenAI GPT Image API."""

from __future__ import annotations

import base64
import os
from pathlib import Path

from openai import OpenAI

from app.config import settings
from app.utils.logging import get_logger

logger = get_logger(__name__)

SIZE_MAP = {
    "landscape": "1792x1024",
    "square": "1024x1024",
    "portrait": "1024x1792",
}


class DSLArtifactService:
    """Generate images from artifact specs using the OpenAI GPT Image API."""

    def __init__(self):
        self.client = OpenAI(api_key=settings.openai_api_key)
        self.image_model = os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-2.5-flare")

    def generate_artifacts(
        self,
        artifact_specs: list,
        output_dir: Path,
    ) -> dict:
        """Generate images for each artifact spec.

        Returns an artifact manifest dict compatible with Remotion's ArtifactManifest:
        {"artifacts": [{"artifactId", "rendererPath", "altText", "approved"}]}
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        manifest_entries = []

        for spec in artifact_specs:
            artifact_id = getattr(spec, "artifact_id", None) or (
                spec.get("artifact_id") if isinstance(spec, dict) else None
            )
            prompt = getattr(spec, "prompt", None) or (
                spec.get("prompt") if isinstance(spec, dict) else None
            )
            orientation = getattr(spec, "orientation", "landscape") or "landscape"

            if not artifact_id or not prompt:
                continue

            size = SIZE_MAP.get(orientation, "1792x1024")
            img_path = output_dir / f"{artifact_id}.png"

            logger.info("Generating artifact %s (%s) with %s…", artifact_id, size, self.image_model)

            try:
                response = self.client.images.generate(
                    model=self.image_model,
                    prompt=prompt,
                    size=size,
                    quality=os.getenv("OPENAI_IMAGE_QUALITY", "high"),
                    output_format="png",
                    n=1,
                )
                encoded = response.data[0].b64_json
                if not encoded:
                    logger.warning("Image API returned no data for %s", artifact_id)
                    continue
                img_path.write_bytes(base64.b64decode(encoded))

                logger.info("  → %s (%.1f KB)", img_path.name, img_path.stat().st_size / 1024)

                manifest_entries.append({
                    "artifactId": artifact_id,
                    "rendererPath": f"artifacts/{artifact_id}.png",
                    "altText": prompt[:120],
                    "approved": True,
                })
            except Exception as exc:
                logger.warning("Artifact generation failed for %s: %s", artifact_id, exc)

        return {"artifacts": manifest_entries}
