"""Tests for TTS provider abstraction (Phase 2 — ElevenLabs scaffold)."""

import pytest


class TestTwilioTTSProvider:
    """Twilio TTS is a pass-through — no audio bytes produced."""

    def test_provider_name(self):
        from app.services.tts.twilio_tts import TwilioTTSProvider

        provider = TwilioTTSProvider()
        assert provider.name == "twilio"

    def test_does_not_support_streaming(self):
        from app.services.tts.twilio_tts import TwilioTTSProvider

        provider = TwilioTTSProvider()
        assert provider.supports_streaming is False

    @pytest.mark.asyncio
    async def test_synthesize_returns_empty_bytes(self):
        from app.services.tts.twilio_tts import TwilioTTSProvider

        provider = TwilioTTSProvider()
        result = await provider.synthesize("Hello, how can I help?", language="en")
        assert result == b""

    @pytest.mark.asyncio
    async def test_synthesize_any_language_returns_empty(self):
        from app.services.tts.twilio_tts import TwilioTTSProvider

        provider = TwilioTTSProvider()
        for lang in ["en", "es", "zh", "vi", "ko", "tl"]:
            result = await provider.synthesize("Test", language=lang)
            assert result == b""

    def test_get_voice_for_language(self):
        from app.services.tts.twilio_tts import TwilioTTSProvider

        provider = TwilioTTSProvider()
        assert provider.get_voice_for_language("en") == "en-US-Neural2-F"
        assert provider.get_voice_for_language("es") == "es-US-Neural2-A"
        assert provider.get_voice_for_language("zh") == "cmn-CN-Wavenet-A"
        assert provider.get_voice_for_language("ko") == "ko-KR-Wavenet-A"

    def test_get_voice_unknown_language_returns_none(self):
        from app.services.tts.twilio_tts import TwilioTTSProvider

        provider = TwilioTTSProvider()
        assert provider.get_voice_for_language("xx") is None

    @pytest.mark.asyncio
    async def test_synthesize_stream_yields_empty(self):
        from app.services.tts.twilio_tts import TwilioTTSProvider

        provider = TwilioTTSProvider()
        chunks = [c async for c in provider.synthesize_stream("Hello")]
        assert chunks == [b""]


class TestElevenLabsTTSProvider:
    """ElevenLabs provider — tests scaffold behavior without real API calls."""

    def test_provider_name(self):
        from app.services.tts.elevenlabs_tts import ElevenLabsTTSProvider

        provider = ElevenLabsTTSProvider(api_key="test_key")
        assert provider.name == "elevenlabs"

    def test_supports_streaming(self):
        from app.services.tts.elevenlabs_tts import ElevenLabsTTSProvider

        provider = ElevenLabsTTSProvider(api_key="test_key")
        assert provider.supports_streaming is True

    def test_default_model_is_flash(self):
        from app.services.tts.elevenlabs_tts import (
            DEFAULT_MODEL,
            ElevenLabsTTSProvider,
        )

        provider = ElevenLabsTTSProvider(api_key="test_key")
        assert provider._model_id == DEFAULT_MODEL
        assert "flash" in DEFAULT_MODEL

    def test_voice_override(self):
        from app.services.tts.elevenlabs_tts import ElevenLabsTTSProvider

        custom_voice = "custom_voice_abc123"
        provider = ElevenLabsTTSProvider(api_key="test_key", voice_id=custom_voice)
        assert provider._voice_id == custom_voice

    def test_get_voice_for_language_returns_voice(self):
        from app.services.tts.elevenlabs_tts import ElevenLabsTTSProvider

        provider = ElevenLabsTTSProvider(api_key="test_key")
        for lang in ["en", "es", "zh", "vi", "ko"]:
            assert provider.get_voice_for_language(lang) is not None

    def test_get_client_raises_without_sdk(self, monkeypatch):
        """If elevenlabs SDK is not installed, raise a helpful error."""
        import builtins

        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "elevenlabs.client":
                raise ImportError("No module named 'elevenlabs'")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", mock_import)

        from app.services.tts.elevenlabs_tts import ElevenLabsTTSProvider

        provider = ElevenLabsTTSProvider(api_key="test_key")
        provider._client = None  # reset lazy-loaded client

        with pytest.raises(RuntimeError, match="pip install elevenlabs"):
            provider._get_client()

    @pytest.mark.asyncio
    async def test_synthesize_raises_without_sdk(self, monkeypatch):
        """Calling synthesize without SDK raises RuntimeError."""
        import builtins

        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "elevenlabs.client":
                raise ImportError("No module named 'elevenlabs'")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", mock_import)

        from app.services.tts.elevenlabs_tts import ElevenLabsTTSProvider

        provider = ElevenLabsTTSProvider(api_key="test_key")
        provider._client = None

        with pytest.raises(RuntimeError, match="pip install elevenlabs"):
            await provider.synthesize("Test")


class TestTTSProviderFactory:
    """get_tts_provider() returns correct provider based on config."""

    def test_returns_twilio_without_api_key(self, monkeypatch):
        from app.config import settings
        from app.services.tts import get_tts_provider
        from app.services.tts.twilio_tts import TwilioTTSProvider

        monkeypatch.setattr(settings, "elevenlabs_api_key", "")
        provider = get_tts_provider()
        assert isinstance(provider, TwilioTTSProvider)

    def test_returns_elevenlabs_with_api_key(self, monkeypatch):
        from app.config import settings
        from app.services.tts import get_tts_provider
        from app.services.tts.elevenlabs_tts import ElevenLabsTTSProvider

        monkeypatch.setattr(settings, "elevenlabs_api_key", "sk_test_1234567890")
        provider = get_tts_provider()
        assert isinstance(provider, ElevenLabsTTSProvider)
        assert provider._api_key == "sk_test_1234567890"


class TestConfig:
    """Config correctly exposes TTS provider name."""

    def test_tts_provider_name_without_key(self, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "elevenlabs_api_key", "")
        assert settings.tts_provider_name == "twilio"

    def test_tts_provider_name_with_key(self, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "elevenlabs_api_key", "sk_real_key")
        assert settings.tts_provider_name == "elevenlabs"
