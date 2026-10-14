from types import SimpleNamespace

from app.schemas.artifact_plan import ArtifactStatus, ArtifactType
from app.services.artifact_service import ArtifactService


def test_logo_asset_type_alias_is_recognized():
    assert ArtifactService._normalise_artifact_type("logo-assets") == ArtifactType.LOGO


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
