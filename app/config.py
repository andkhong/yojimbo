from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False
    secret_key: str = "change-me-to-a-random-secret-key"
    base_url: str = "http://localhost:8000"

    # Database
    database_url: str = "sqlite+aiosqlite:///./yojimbo.db"

    # Twilio
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_phone_number: str = ""

    # Google Gemini
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"
    gemini_temperature: float = 0.3
    gemini_max_tokens: int = 500

    # Google Cloud Translation
    google_cloud_project_id: str = ""

    # ConversationRelay
    cr_tts_provider: str = "google"
    cr_stt_provider: str = "google"
    cr_welcome_greeting: str = (
        "Hello, thank you for calling. How can I help you today?"
    )

    # ElevenLabs TTS (Phase 2 — optional, replaces Twilio TTS)
    # Set ELEVENLABS_API_KEY to enable. Leave blank to use Twilio built-in TTS.
    elevenlabs_api_key: str = ""
    elevenlabs_voice_id: str = "21m00Tcm4TlvDq8ikWAM"    # Rachel — warm, professional
    elevenlabs_model_id: str = "eleven_flash_v2_5"         # Lowest latency model

    @property
    def tts_provider_name(self) -> str:
        """Returns active TTS provider name based on config."""
        return "elevenlabs" if self.elevenlabs_api_key else "twilio"

    # Government Office
    office_name: str = "City Hall"
    default_language: str = "en"
    supported_languages: str = "en,es,zh,vi,ko,tl,ar,fr,de,ja"

    @property
    def supported_languages_list(self) -> list[str]:
        return [lang.strip() for lang in self.supported_languages.split(",")]

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
