"""Twilio Media Stream WebSocket handler (Phase 2 — ElevenLabs TTS path).

Architecture (ElevenLabs path):
    Caller → Twilio PSTN
        → Twilio <Stream> WebSocket (raw mulaw audio)
        → This handler
            → STT: Twilio built-in (via ConversationRelay) or Deepgram (future)
            → AI:  Google Gemini (function calling, appointment booking)
            → TTS: ElevenLabs (sub-100ms, neural voices, 32 languages)
        → Audio stream back to Twilio → Caller

vs. ConversationRelay path (Phase 1 / fallback):
    Caller → Twilio PSTN
        → Twilio ConversationRelay (STT + TTS handled by Twilio)
        → conversation_relay.py WebSocket
            → AI: Google Gemini
        → Text response → Twilio TTS → Caller

Toggle:
    Set ELEVENLABS_API_KEY in .env to activate this path.
    Without the key, the app routes to conversation_relay.py automatically.

Status: SCAFFOLD — ready for ElevenLabs API key activation.
        Add Deepgram or similar STT for full audio streaming capability.
"""

import base64
import json
import logging
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

from app.config import settings
from app.services.tts import get_tts_provider

logger = logging.getLogger(__name__)


class MediaStreamSession:
    """Manages a single Twilio Media Stream conversation session."""

    def __init__(self, stream_sid: str, call_sid: str):
        self.stream_sid = stream_sid
        self.call_sid = call_sid
        self.tts = get_tts_provider()
        self._audio_buffer = bytearray()
        self._silence_threshold = 0.5  # seconds of silence before processing

    async def process_text_response(
        self,
        text: str,
        language: str = "en",
        websocket: WebSocket | None = None,
    ) -> None:
        """Synthesize text via ElevenLabs and stream back to Twilio.

        For the ElevenLabs provider: streams audio chunks to Twilio
        as base64-encoded mulaw via the Media Stream protocol.

        For the Twilio provider: no-op (Twilio handles TTS itself).
        """
        if self.tts.name == "twilio":
            logger.debug("TwilioTTS: text will be spoken by Twilio ConversationRelay")
            return

        if not websocket:
            return

        logger.info(
            "ElevenLabs TTS: synthesizing %d chars in language=%s",
            len(text),
            language,
        )

        chunk_count = 0
        async for chunk in self.tts.synthesize_stream(text, language=language):
            # Twilio Media Stream expects base64-encoded audio payloads
            payload = base64.b64encode(chunk).decode("utf-8")
            await websocket.send_text(
                json.dumps({
                    "event": "media",
                    "streamSid": self.stream_sid,
                    "media": {
                        "payload": payload,
                    },
                })
            )
            chunk_count += 1

        # Send mark to know when audio finishes playing
        await websocket.send_text(
            json.dumps({
                "event": "mark",
                "streamSid": self.stream_sid,
                "mark": {"name": "response_end"},
            })
        )
        logger.debug("ElevenLabs TTS: streamed %d chunks to Twilio", chunk_count)


# Active media stream sessions
_active_streams: dict[str, MediaStreamSession] = {}


async def handle_media_stream(websocket: WebSocket) -> None:
    """Handle a Twilio Media Stream WebSocket connection.

    This is the Phase 2 entry point when ELEVENLABS_API_KEY is configured.
    Currently scaffolded — full STT integration (Deepgram) is Phase 3.
    """
    await websocket.accept()
    session: MediaStreamSession | None = None

    logger.info(
        "Media stream connected — TTS provider: %s",
        settings.tts_provider_name,
    )

    try:
        async for raw_message in websocket.iter_text():
            try:
                message: dict[str, Any] = json.loads(raw_message)
            except json.JSONDecodeError:
                continue

            event = message.get("event")

            if event == "connected":
                logger.info("Twilio Media Stream connected: %s", message)

            elif event == "start":
                start = message.get("start", {})
                stream_sid = start.get("streamSid", "")
                call_sid = start.get("callSid", "")
                session = MediaStreamSession(stream_sid=stream_sid, call_sid=call_sid)
                _active_streams[stream_sid] = session
                logger.info(
                    "Media stream started: streamSid=%s callSid=%s provider=%s",
                    stream_sid,
                    call_sid,
                    session.tts.name,
                )

            elif event == "media" and session:
                # TODO Phase 3: pipe audio to Deepgram STT
                # chunk = base64.b64decode(message["media"]["payload"])
                # await stt.feed_audio(chunk)
                pass

            elif event == "mark":
                logger.debug("Media stream mark: %s", message.get("mark", {}).get("name"))

            elif event == "stop":
                logger.info(
                    "Media stream stopped: %s",
                    message.get("stop", {}).get("streamSid"),
                )
                break

    except WebSocketDisconnect:
        logger.info("Media stream WebSocket disconnected")
    except Exception:
        logger.exception("Error in media stream handler")
    finally:
        if session and session.stream_sid in _active_streams:
            del _active_streams[session.stream_sid]
