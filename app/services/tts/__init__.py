"""TTS provider factory.

Usage:
    from app.services.tts import get_tts_provider
    tts = get_tts_provider()
    audio_bytes = await tts.synthesize("Hello, how can I help?", language="es")

Provider selection:
    - Set ELEVENLABS_API_KEY in .env to enable ElevenLabs (recommended)
    - Without key, falls back to Twilio ConversationRelay built-in TTS (free, lower quality)
"""

from app.config import settings
from app.services.tts.base import TTSProvider
from app.services.tts.twilio_tts import TwilioTTSProvider


def get_tts_provider() -> TTSProvider:
    """Return the best available TTS provider based on config."""
    if settings.elevenlabs_api_key:
        from app.services.tts.elevenlabs_tts import ElevenLabsTTSProvider

        return ElevenLabsTTSProvider(
            api_key=settings.elevenlabs_api_key,
            voice_id=settings.elevenlabs_voice_id,
            model_id=settings.elevenlabs_model_id,
        )
    return TwilioTTSProvider()


__all__ = ["get_tts_provider", "TTSProvider"]
