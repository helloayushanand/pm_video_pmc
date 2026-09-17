"""OpenAI services for dossier extraction and video planning."""

from __future__ import annotations

import base64
import json
from pathlib import Path

from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import PROMPTS_DIR, settings
from app.schemas.dossier import Dossier
from app.schemas.storyboard import Storyboard
from app.schemas.video_content import VideoContent
from app.utils.json_utils import load_json, save_json
from app.utils.logging import get_logger


logger = get_logger(__name__)


class VLMServiceError(Exception):
    """Base exception for OpenAI processing errors."""


class VLMConfigurationError(VLMServiceError):
    """Raised when OpenAI configuration is incomplete."""


class VLMInputError(VLMServiceError):
    """Raised when input artifacts are missing or invalid."""


class VLMExtractionError(VLMServiceError):
    """Raised when structured output generation fails."""


class OpenAIVLMService:
    """Generate structured pipeline outputs using OpenAI."""

    def __init__(
        self,
        api_key=None,
        model=None,
        prompt_path=None,
        max_pages=None,
        image_detail="high",
    ):
        self.api_key = api_key or settings.openai_api_key
        self.model = model or settings.openai_model
        self.prompt_path = Path(
            prompt_path or PROMPTS_DIR / "dossier_extraction.txt"
        )
        self.max_pages = max_pages
        self.image_detail = image_detail

        if not self.api_key:
            raise VLMConfigurationError(
                "OPENAI_API_KEY is not configured in .env."
            )

        if not self.model:
            raise VLMConfigurationError(
                "OPENAI_MODEL is not configured."
            )

        if self.image_detail not in {"low", "high", "auto"}:
            raise VLMConfigurationError(
                "image_detail must be low, high, or auto."
            )

        self.client = OpenAI(api_key=self.api_key)

    # --------------------------------------------------------
    # DOSSIER EXTRACTION
    # --------------------------------------------------------

    def extract_dossier(
        self,
        document_directory,
        output_directory,
    ):
        """Extract a structured Dossier from prepared PDF pages."""

        document_path = Path(document_directory).resolve()
        output_path = Path(output_directory).resolve()
        output_path.mkdir(parents=True, exist_ok=True)

        document_json_path = document_path / "document.json"
        native_text_path = document_path / "native_text.json"

        if not document_json_path.exists():
            raise VLMInputError(
                f"Document metadata not found: {document_json_path}"
            )

        if not native_text_path.exists():
            raise VLMInputError(
                f"Native text not found: {native_text_path}"
            )

        prompt_path = PROMPTS_DIR / "dossier_extraction.txt"

        if not prompt_path.exists():
            raise VLMInputError(
                f"Extraction prompt not found: {prompt_path}"
            )

        document_metadata = load_json(document_json_path)
        native_text = load_json(native_text_path)

        pages = self._load_document_pages(
            document_directory=document_path,
            document_metadata=document_metadata,
            native_text=native_text,
        )

        prompt = prompt_path.read_text(
            encoding="utf-8-sig"
        ).strip()

        request_manifest = {
            "provider": "openai",
            "operation": "dossier_extraction",
            "model": self.model,
            "document_id": document_metadata.get("document_id"),
            "page_count_submitted": len(pages),
            "image_detail": self.image_detail,
            "pages": [
                {
                    "page_number": page["page_number"],
                    "image_path": str(page["image_path"]),
                    "native_text_character_count": len(
                        page["native_text"]
                    ),
                }
                for page in pages
            ],
        }

        save_json(
            request_manifest,
            output_path / "extraction_request.json",
        )

        user_content = self._build_extraction_content(
            pages=pages,
            document_metadata=document_metadata,
        )

        logger.info(
            "Submitting %s dossier pages to OpenAI model %s.",
            len(pages),
            self.model,
        )

        try:
            response = self._parse_response(
                prompt=prompt,
                user_content=user_content,
                output_model=Dossier,
            )
        except Exception as error:
            raise VLMExtractionError(
                f"OpenAI dossier extraction failed: {error}"
            ) from error

        self._save_response(
            response,
            output_path / "dossier_raw_response.json",
        )

        dossier = response.output_parsed

        if dossier is None:
            raise VLMExtractionError(
                "OpenAI returned no parsed dossier."
            )

        if not isinstance(dossier, Dossier):
            dossier = Dossier.model_validate(dossier)

        dossier.metadata.document_id = document_metadata.get(
            "document_id"
        )
        dossier.metadata.original_filename = (
            document_metadata.get("original_filename")
        )
        dossier.metadata.page_count = document_metadata.get(
            "page_count"
        )
        dossier.metadata.extraction_model = self.model

        dossier_path = output_path / "dossier_extracted.json"

        save_json(
            dossier.model_dump(mode="json"),
            dossier_path,
        )

        metadata = self._response_metadata(
            response=response,
            operation="dossier_extraction",
        )

        metadata.update(
            {
                "document_id": document_metadata.get("document_id"),
                "page_count_submitted": len(pages),
                "output_file": str(dossier_path),
            }
        )

        save_json(
            metadata,
            output_path / "extraction_metadata.json",
        )

        return dossier

    # --------------------------------------------------------
    # VIDEO CONTENT SELECTION
    # --------------------------------------------------------

    def select_video_content(
        self,
        dossier,
        output_directory,
        include_compensation=False,
        include_availability=True,
        video_mode="automatic",
    ):
        """Select sanitised dossier content for video generation."""

        output_path = Path(output_directory).resolve()
        output_path.mkdir(parents=True, exist_ok=True)

        if not isinstance(dossier, Dossier):
            dossier = Dossier.model_validate(dossier)

        prompt_path = PROMPTS_DIR / "content_selection.txt"

        if not prompt_path.exists():
            raise VLMInputError(
                f"Content-selection prompt not found: {prompt_path}"
            )

        prompt = prompt_path.read_text(
            encoding="utf-8-sig"
        ).strip()

        safe_dossier = dossier.model_dump(mode="json")

        settings_block = {
            "video_mode": video_mode,
            "include_compensation": bool(include_compensation),
            "include_availability": bool(include_availability),
        }

        request_manifest = {
            "provider": "openai",
            "operation": "video_content_selection",
            "model": self.model,
            "settings": settings_block,
            "candidate_name": dossier.candidate.full_name,
            "input_schema": "Dossier",
            "output_schema": "VideoContent",
        }

        save_json(
            request_manifest,
            output_path / "selection_request.json",
        )

        user_text = (
            "Create approved video content from the structured "
            "candidate dossier below.\n\n"
            "GENERATION SETTINGS\n"
            f"{json.dumps(settings_block, indent=2)}\n\n"
            "STRUCTURED DOSSIER\n"
            f"{json.dumps(safe_dossier, ensure_ascii=False)}"
        )

        try:
            response = self._parse_response(
                prompt=prompt,
                user_content=[
                    {
                        "type": "input_text",
                        "text": user_text,
                    }
                ],
                output_model=VideoContent,
            )
        except Exception as error:
            raise VLMExtractionError(
                f"Video-content selection failed: {error}"
            ) from error

        self._save_response(
            response,
            output_path / "selection_raw_response.json",
        )

        video_content = response.output_parsed

        if video_content is None:
            raise VLMExtractionError(
                "OpenAI returned no parsed VideoContent."
            )

        if not isinstance(video_content, VideoContent):
            video_content = VideoContent.model_validate(
                video_content
            )

        if not include_compensation:
            video_content.optional_details.include_compensation = False
            video_content.optional_details.compensation_summary = None

        if not include_availability:
            video_content.optional_details.include_availability = False
            video_content.optional_details.availability_summary = None

        save_json(
            video_content.model_dump(mode="json"),
            output_path / "video_content.json",
        )

        metadata = self._response_metadata(
            response=response,
            operation="video_content_selection",
        )

        metadata["selected_highlight_count"] = len(
            video_content.selected_highlights
        )
        metadata["career_milestone_count"] = len(
            video_content.career_milestones
        )

        save_json(
            metadata,
            output_path / "selection_metadata.json",
        )

        return video_content

    # --------------------------------------------------------
    # STORYBOARD GENERATION
    # --------------------------------------------------------

    def generate_storyboard(
        self,
        video_content,
        output_directory,
    ):
        """Generate a structured storyboard from approved content."""

        output_path = Path(output_directory).resolve()
        output_path.mkdir(parents=True, exist_ok=True)

        if not isinstance(video_content, VideoContent):
            video_content = VideoContent.model_validate(
                video_content
            )

        prompt_path = PROMPTS_DIR / "storyboard_generation.txt"

        if not prompt_path.exists():
            raise VLMInputError(
                f"Storyboard prompt not found: {prompt_path}"
            )

        prompt = prompt_path.read_text(
            encoding="utf-8-sig"
        ).strip()

        request_manifest = {
            "provider": "openai",
            "operation": "storyboard_generation",
            "model": self.model,
            "candidate_name": video_content.candidate_intro.name,
            "input_schema": "VideoContent",
            "output_schema": "Storyboard",
            "recommended_duration_seconds": (
                video_content.recommended_duration_seconds
            ),
        }

        save_json(
            request_manifest,
            output_path / "storyboard_request.json",
        )

        user_text = (
            "Create a video storyboard from the approved and "
            "sanitised content below.\n\n"
            "APPROVED VIDEO CONTENT\n"
            f"{json.dumps(video_content.model_dump(mode='json'), ensure_ascii=False)}"
        )

        try:
            response = self._parse_response(
                prompt=prompt,
                user_content=[
                    {
                        "type": "input_text",
                        "text": user_text,
                    }
                ],
                output_model=Storyboard,
            )
        except Exception as error:
            raise VLMExtractionError(
                f"Storyboard generation failed: {error}"
            ) from error

        self._save_response(
            response,
            output_path / "storyboard_raw_response.json",
        )

        storyboard = response.output_parsed

        if storyboard is None:
            raise VLMExtractionError(
                "OpenAI returned no parsed Storyboard."
            )

        if not isinstance(storyboard, Storyboard):
            storyboard = Storyboard.model_validate(
                storyboard
            )

        save_json(
            storyboard.model_dump(mode="json"),
            output_path / "storyboard.json",
        )

        metadata = self._response_metadata(
            response=response,
            operation="storyboard_generation",
        )

        metadata["scene_count"] = len(storyboard.scenes)
        metadata["estimated_duration_seconds"] = (
            storyboard.estimated_total_duration_seconds
        )

        save_json(
            metadata,
            output_path / "storyboard_metadata.json",
        )

        return storyboard

    # --------------------------------------------------------
    # OPENAI REQUEST
    # --------------------------------------------------------

    @retry(
        wait=wait_exponential(
            multiplier=2,
            min=2,
            max=20,
        ),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    def _parse_response(
        self,
        prompt,
        user_content,
        output_model,
    ):
        """Call OpenAI and parse the result into a Pydantic model."""

        return self.client.responses.parse(
            model=self.model,
            instructions=prompt,
            input=[
                {
                    "role": "user",
                    "content": user_content,
                }
            ],
            text_format=output_model,
        )

    # --------------------------------------------------------
    # INPUT CONSTRUCTION
    # --------------------------------------------------------

    def _load_document_pages(
        self,
        document_directory,
        document_metadata,
        native_text,
    ):
        """Resolve prepared dossier pages."""

        metadata_pages = document_metadata.get("pages", [])
        text_pages = native_text.get("pages", [])

        text_by_page = {
            page.get("page_number"): page.get("text", "")
            for page in text_pages
        }

        if self.max_pages is not None:
            metadata_pages = metadata_pages[: self.max_pages]

        if not metadata_pages:
            raise VLMInputError(
                "No page metadata was found."
            )

        pages = []

        for metadata in metadata_pages:
            page_number = metadata.get("page_number")
            relative_image_path = metadata.get("image_path")

            if page_number is None:
                raise VLMInputError(
                    "A page is missing page_number."
                )

            if not relative_image_path:
                raise VLMInputError(
                    f"Page {page_number} is missing image_path."
                )

            image_path = (
                document_directory / relative_image_path
            ).resolve()

            if not image_path.exists():
                raise VLMInputError(
                    f"Page image not found: {image_path}"
                )

            pages.append(
                {
                    "page_number": page_number,
                    "image_path": image_path,
                    "native_text": text_by_page.get(
                        page_number,
                        "",
                    ),
                }
            )

        return pages

    def _build_extraction_content(
        self,
        pages,
        document_metadata,
    ):
        """Build the multimodal dossier extraction input."""

        content = [
            {
                "type": "input_text",
                "text": (
                    "Extract this confidential candidate dossier "
                    "into the required structured schema.\n"
                    f"Document ID: "
                    f"{document_metadata.get('document_id')}\n"
                    f"Pages submitted: {len(pages)}"
                ),
            }
        ]

        for page in pages:
            native_text = page["native_text"].strip()

            page_text = (
                f"SOURCE PAGE {page['page_number']}\n\n"
                "Native text extracted from the same page:\n\n"
                f"{native_text if native_text else '[No native text]'}"
            )

            content.append(
                {
                    "type": "input_text",
                    "text": page_text,
                }
            )

            content.append(
                {
                    "type": "input_image",
                    "image_url": self._image_as_data_url(
                        page["image_path"]
                    ),
                    "detail": self.image_detail,
                }
            )

        return content

    # --------------------------------------------------------
    # HELPERS
    # --------------------------------------------------------

    @staticmethod
    def _image_as_data_url(image_path):
        """Encode a local page image as a data URL."""

        path = Path(image_path)

        mime_types = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
        }

        mime_type = mime_types.get(path.suffix.lower())

        if mime_type is None:
            raise VLMInputError(
                f"Unsupported image type: {path.suffix}"
            )

        encoded = base64.b64encode(
            path.read_bytes()
        ).decode("ascii")

        return f"data:{mime_type};base64,{encoded}"

    @staticmethod
    def _save_response(response, output_path):
        """Save the complete provider response locally."""

        if hasattr(response, "model_dump"):
            data = response.model_dump(mode="json")
        elif hasattr(response, "json"):
            data = json.loads(response.json())
        else:
            data = {"response": str(response)}

        save_json(data, output_path)

    def _response_metadata(
        self,
        response,
        operation,
    ):
        """Create non-content response metadata."""

        metadata = {
            "provider": "openai",
            "operation": operation,
            "model": self.model,
            "response_id": getattr(response, "id", None),
            "status": "completed",
        }

        usage = getattr(response, "usage", None)

        if usage is not None:
            if hasattr(usage, "model_dump"):
                metadata["usage"] = usage.model_dump()
            else:
                metadata["usage"] = str(usage)

        return metadata
