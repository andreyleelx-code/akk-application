import httpx
import pytest

from carval.models import Car, Defect, Report, Settlement, Severity
from carval.voice import STT_URL, TTS_URL, Voice, VoiceError, spoken_summary


def make_voice(settings, handler, key="k"):
    settings.yandex_api_key = key
    settings.yandex_folder_id = "f"
    return Voice(settings, client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))


async def test_transcribe_sends_ogg_and_returns_text(settings):
    seen = {}

    def handler(req: httpx.Request):
        seen["url"], seen["auth"], seen["body"] = str(req.url), req.headers["Authorization"], req.content
        return httpx.Response(200, json={"result": " Царапина на заднем бампере "})

    v = make_voice(settings, handler)
    assert await v.transcribe(b"OggS...") == "Царапина на заднем бампере"
    assert seen["url"].startswith(STT_URL) and "format=oggopus" in seen["url"] and "folderId=f" in seen["url"]
    assert seen["auth"] == "Api-Key k" and seen["body"] == b"OggS..."


async def test_speak_returns_audio(settings):
    def handler(req: httpx.Request):
        assert str(req.url) == TTS_URL and b"voice=alena" in req.content
        return httpx.Response(200, content=b"OggS-audio")

    assert await make_voice(settings, handler).speak("Привет") == b"OggS-audio"


async def test_voice_disabled_without_key(settings):
    v = make_voice(settings, lambda r: httpx.Response(500), key="")
    assert not v.enabled
    with pytest.raises(VoiceError):
        await v.transcribe(b"x")


async def test_api_error_becomes_voice_error(settings):
    with pytest.raises(VoiceError):
        await make_voice(settings, lambda r: httpx.Response(401)).transcribe(b"x")


def test_spoken_summary_for_return(camry):
    d = Defect(zone="body", code="dent", severity=Severity.minor, angle_id="left", location="x",
               description="", confidence=0.9)
    r = Report(kind="return", car=camry, defects=[d], needs_manual_review=False,
               settlement=Settlement(new_defect_ids=[d.id], total=42000, deposit=30000, due=12000))
    text = spoken_summary(r)
    assert "Новых с момента выдачи: 1" in text and "42 000" in text and "12 000" in text
