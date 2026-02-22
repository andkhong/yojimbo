"""Abstract TTS provider interface."""

from abc import ABC, abstractmethod


class TTSProvider(ABC):
    """Base class for all TTS providers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable provider name."""

    @property
    @abstractmethod
    def supports_streaming(self) -> bool:
        """True if provider supports real-time audio streaming."""

    @abstractmethod
    async def synthesize(
        self,
        text: str,
        language: str = "en",
        voice_id: str | None = None,
    ) -> bytes:
        """Convert text to audio bytes (PCM/MP3).

        Args:
            text: Text to speak.
            language: BCP-47 language code (e.g. 'en', 'es', 'zh').
            voice_id: Optional voice override. Provider-specific.

        Returns:
            Raw audio bytes.
        """

    async def synthesize_stream(
        self,
        text: str,
        language: str = "en",
        voice_id: str | None = None,
    ):
        """Async generator yielding audio chunks for streaming.

        Default implementation: synthesize fully then yield in one chunk.
        Override for true streaming support.
        """
        audio = await self.synthesize(text, language=language, voice_id=voice_id)
        yield audio

    def get_voice_for_language(self, language: str) -> str | None:
        """Return a recommended voice ID for the given language code.

        Override in subclass to provide language-specific voice mapping.
        """
        return None
