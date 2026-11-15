import json
from pathlib import Path

import httpx
import pytest

from shms.detection.base import HazardDetector
from shms.detection.mock import MockDetector
from shms.detection.ollama_vlm import OllamaDetector, parse_answer
from tests.conftest import jpeg_bytes

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture()
def photo(tmp_path):
    p = tmp_path / "photo.jpg"
    p.write_bytes(jpeg_bytes(size=(3000, 2000)))
    return p


def test_mock_is_deterministic(photo):
    a, b = MockDetector().detect(photo), MockDetector().detect(photo)
    assert a.codes() == b.codes() and a.error is None and a.latency_ms >= 0


def test_failing_detector_returns_error_instead_of_raising(photo):
    class Broken(HazardDetector):
        name = "broken"

        def _predict(self, image_path):
            raise RuntimeError("model crashed")

    r = Broken().detect(photo)
    assert r.error == "RuntimeError: model crashed" and r.suggestions == []


def test_parse_vlm_answer():
    s = parse_answer(
        json.dumps(
            {
                "people_visible": True,
                "worker_without_hard_hat": True,
                "worker_without_eye_protection": True,
                "worker_without_hi_vis_vest": False,
                "bare_hands_visible": True,
                "confidence": 0.9,
                "explanation": "man welding, bare head",
            }
        )
    )
    assert {x.code for x in s} == {"no_hard_hat", "no_eye_protection", "no_gloves"} and s[0].confidence == 0.9


def test_parse_vlm_answer_clamps_bad_confidence():
    s = parse_answer(json.dumps({"worker_without_hard_hat": True, "confidence": "high"}))
    assert s[0].confidence == 0.7


def test_ollama_detector_request_and_downscale(photo):
    seen = {}

    def handler(request: httpx.Request):
        body = json.loads(request.content)
        seen.update(body)
        answer = {
            "people_visible": True,
            "worker_without_hard_hat": False,
            "worker_without_hi_vis_vest": True,
            "bare_hands_visible": False,
            "confidence": 0.8,
            "explanation": "no vest",
        }
        return httpx.Response(200, json={"message": {"content": json.dumps(answer)}})

    det = OllamaDetector("qwen2.5vl:7b", client=httpx.Client(transport=httpx.MockTransport(handler)))
    r = det.detect(photo)
    assert r.error is None and r.codes() == {"no_hi_vis_vest"} and r.model == "ollama:qwen2.5vl:7b"
    assert seen["model"] == "qwen2.5vl:7b" and seen["options"]["temperature"] == 0
    assert seen["format"]["required"]  # JSON schema enforced
    import base64
    import io

    from PIL import Image

    img = Image.open(io.BytesIO(base64.b64decode(seen["messages"][0]["images"][0])))
    assert max(img.size) <= 1024  # large photos are downscaled before sending


def test_ollama_unreachable_is_reported(photo):
    def handler(request):
        raise httpx.ConnectError("connection refused")

    det = OllamaDetector("m", client=httpx.Client(transport=httpx.MockTransport(handler)))
    r = det.detect(photo)
    assert r.error and "ConnectError" in r.error


@pytest.mark.skipif(not (ROOT / "models" / "sh17_yolo8s.pt").is_file(), reason="SH17 weights not downloaded")
def test_yolo_detector_runs_on_a_photo(photo):
    pytest.importorskip("ultralytics")
    from shms.detection.yolo import YoloDetector

    r = YoloDetector(ROOT / "models" / "sh17_yolo8s.pt", device="cpu").detect(photo)
    assert r.error is None and r.model == "yolo:sh17_yolo8s"


def test_yolo_missing_weights_message(tmp_path):
    pytest.importorskip("ultralytics")
    from shms.detection.yolo import YoloDetector

    with pytest.raises(FileNotFoundError, match="download_models"):
        YoloDetector(tmp_path / "nope.pt")
