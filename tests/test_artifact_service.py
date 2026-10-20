from types import SimpleNamespace

from app.schemas.artifact_plan import ArtifactStatus, ArtifactType
from app.services.artifact_service import ArtifactService


def test_logo_asset_type_alias_is_recognized():
    assert ArtifactService._normalise_artifact_type("logo-assets") == ArtifactType.LOGO


def test_portrait_asset_type_alias_is_recognized():
    assert ArtifactService._normalise_artifact_type("portrait_asset") == ArtifactType.PORTRAIT


def test_illustrated_portrait_asset_type_alias_is_recognized():
    assert ArtifactService._normalise_artifact_type("illustrated_portrait") == ArtifactType.PORTRAIT


def test_unverified_portrait_candidate_uses_fallback(tmp_path, monkeypatch):
    candidate = tmp_path / "placeholder.png"
    from PIL import Image

    Image.new("RGB", (144, 219), "#f47708").save(candidate)
    service = ArtifactService()
    monkeypatch.setattr(service, "client", None)
    record = service._prepare_auto_local_asset(
        artifact=SimpleNamespace(artifact_type=ArtifactType.PORTRAIT),
        base_kwargs={
            "artifact_id": "candidate_portrait",
            "scene_id": "scene_intro",
            "artifact_type": ArtifactType.PORTRAIT,
            "source_strategy": "approved_local_asset",
            "factual_status": "factual",
            "required": True,
            "alt_text": "Candidate portrait",
            "fallback_strategy": "Use a typography-led introduction.",
        },
        extracted_candidates=[
            {
                "path": str(candidate),
                "filename": "placeholder.png",
                "portrait_likelihood": 0.7,
                "is_candidate_portrait": False,
            }
        ],
        approved_directory=tmp_path / "approved",
    )

    assert record.status == ArtifactStatus.FALLBACK
    assert not record.approved
    assert record.local_path is None
    assert "visually verified" in record.source_description


def test_visual_selector_finds_portrait_after_non_portrait_candidate(tmp_path):
    from PIL import Image

    first_image = tmp_path / "frame.png"
    second_image = tmp_path / "headshot.png"
    Image.new("RGB", (144, 219), "#f47708").save(first_image)
    Image.new("RGB", (400, 400), "#223344").save(second_image)
    service = ArtifactService()

    class FakeResponses:
        @staticmethod
        def parse(**kwargs):
            images = [
                item
                for item in kwargs["input"][0]["content"]
                if item["type"] == "input_image"
            ]
            assert len(images) == 2
            return SimpleNamespace(
                output_parsed=SimpleNamespace(
                    candidate_id="headshot",
                    confidence=0.98,
                )
            )

    service.client = SimpleNamespace(responses=FakeResponses())
    candidates = [
        {
            "candidate_id": "frame",
            "filename": "frame.png",
            "path": str(first_image),
        },
        {
            "candidate_id": "headshot",
            "filename": "headshot.png",
            "path": str(second_image),
        },
    ]

    selected = service._select_candidate_portrait(candidates)

    assert selected is candidates[1]
    assert selected["portrait_detection_confidence"] == 0.98


def test_verified_portrait_selection_overrides_geometry_score(tmp_path):
    from PIL import Image

    placeholder_path = tmp_path / "placeholder.png"
    portrait_path = tmp_path / "portrait.png"
    approved_directory = tmp_path / "approved"
    approved_directory.mkdir()
    Image.new("RGB", (144, 219), "#f47708").save(placeholder_path)
    Image.new("RGB", (400, 400), "#223344").save(portrait_path)
    record = ArtifactService()._prepare_auto_local_asset(
        artifact=SimpleNamespace(
            artifact_id="candidate_portrait",
            artifact_type=ArtifactType.PORTRAIT,
        ),
        base_kwargs={
            "artifact_id": "candidate_portrait",
            "scene_id": "scene_intro",
            "artifact_type": ArtifactType.PORTRAIT,
            "source_strategy": "approved_local_asset",
            "factual_status": "factual",
            "required": True,
            "alt_text": "Candidate portrait",
            "fallback_strategy": "Typography-only intro.",
        },
        extracted_candidates=[
            {
                "path": str(placeholder_path),
                "filename": "placeholder.png",
                "portrait_likelihood": 0.7,
                "is_candidate_portrait": False,
            },
            {
                "path": str(portrait_path),
                "filename": "portrait.png",
                "portrait_likelihood": 0.3,
                "is_candidate_portrait": True,
            },
        ],
        approved_directory=approved_directory,
    )

    assert record.status == ArtifactStatus.APPROVED
    assert record.approved
    assert record.width == 400
    assert "portrait.png" in record.source_description


def test_candidate_portrait_updates_intro_artifact_requirement():
    creative_plan = {
        "draft": {
            "creative_direction": {
                "image_treatment": "Illustrated portrait",
                "prohibited_treatments": ["candidate photography"],
            },
            "scene_briefs": [
                {
                    "scene_id": "scene_01_intro",
                    "scene_type": "candidate_intro",
                    "visual_story": "Illustrated portrait on the left.",
                    "layout_intent": "Large illustrated portrait beside the name.",
                    "artifact_requirements": [
                        {
                            "artifact_id": "art_intro_portrait_01",
                            "artifact_type": "illustrated_portrait",
                            "source_strategy": "image_generation",
                            "factual_status": "decorative",
                            "purpose": "Illustrated portrait",
                            "visual_brief": "Stylised portrait.",
                            "fallback_strategy": "typography_only",
                        }
                    ],
                }
            ],
        }
    }

    ArtifactService._configure_candidate_portrait(
        creative_plan,
        creative_plan["draft"],
    )

    intro = creative_plan["draft"]["scene_briefs"][0]
    portrait = intro["artifact_requirements"][0]
    assert portrait["artifact_id"] == "art_intro_portrait_01"
    assert portrait["artifact_type"] == "portrait"
    assert portrait["source_strategy"] == "approved_local_asset"
    assert intro["visual_story"] == "Candidate headshot on the left."
    assert creative_plan["draft"]["creative_direction"]["prohibited_treatments"] == []
    plan = ArtifactService()._build_plan(
        candidate_name="Candidate",
        creative_direction=creative_plan["draft"]["creative_direction"],
        scene_briefs=creative_plan["draft"]["scene_briefs"],
        global_notes=[],
    )
    assert plan.artifacts[0].artifact_type == ArtifactType.PORTRAIT


def test_arbitrary_extracted_image_is_not_approved_as_employer_logo(tmp_path):
    record = ArtifactService()._prepare_auto_local_asset(
        artifact=SimpleNamespace(artifact_type=ArtifactType.LOGO),
        base_kwargs={
            "artifact_id": "employer_logos",
            "scene_id": "scene_timeline",
            "artifact_type": ArtifactType.LOGO,
            "source_strategy": "approved_local_asset",
            "factual_status": "factual",
            "required": False,
            "alt_text": "Employer logos",
            "fallback_strategy": "Render employer names as text.",
        },
        extracted_candidates=[
            {
                "path": str(tmp_path / "unrelated.png"),
                "filename": "unrelated.png",
            }
        ],
        approved_directory=tmp_path,
    )

    assert record.status == ArtifactStatus.FALLBACK
    assert not record.approved
    assert record.local_path is None
    assert "not automatically treated as logos" in record.validation_warnings[0]
