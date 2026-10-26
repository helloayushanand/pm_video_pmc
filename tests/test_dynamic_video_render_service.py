"""Tests for Phase 7B media and scene helpers."""
from app.services.dynamic_video_render_service import DynamicVideoRenderService


def test_has_stream():
    probe = {
        "streams": [
            {"codec_type": "video"},
            {"codec_type": "audio"},
        ]
    }
    assert DynamicVideoRenderService._has_stream(probe, "video")
    assert DynamicVideoRenderService._has_stream(probe, "audio")


def test_video_fps():
    probe = {
        "streams": [
            {
                "codec_type": "video",
                "avg_frame_rate": "30/1",
            }
        ]
    }
    assert DynamicVideoRenderService._video_fps(probe) == 30


def test_duration_from_format():
    probe = {
        "format": {"duration": "12.5"},
        "streams": [],
    }
    assert DynamicVideoRenderService._duration(probe) == 12.5
