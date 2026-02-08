"""SMS conversation handler using Google Gemini."""

import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.constants import LANGUAGE_NAMES
from app.core.prompts import SMS_SYSTEM_PROMPT
from app.models.department import Department
from app.models.message import SMSMessage
from app.services import appointment_engine, translator

logger = logging.getLogger(__name__)


async def handle_inbound_sms(
    db: AsyncSession,
    from_number: str,
    body: str,
    message_sid: str,
) -> str:
    """Process an inbound SMS and return the reply text."""
    # Detect language
    detected_lang = await translator.detect_language(body)

    # Translate to English if needed
    english_text = body
    if detected_lang != "en":
        english_text = await translator.translate_text(body, "en", detected_lang)

    # Get or create contact
    contact = await appointment_engine.get_or_create_contact(
        db, from_number, language=detected_lang
    )

    # Store the inbound message
    sms = SMSMessage(
        twilio_message_sid=message_sid,
        contact_id=contact.id,
        direction="inbound",
        body=body,
        translated_body=english_text if detected_lang != "en" else None,
        detected_language=detected_lang,
        status="received",
    )
    db.add(sms)

    # Generate AI response
    response_text = await _generate_sms_response(db, english_text, detected_lang)

    # Translate response if needed
    if detected_lang != "en":
        response_text = await translator.translate_text(
            response_text, detected_lang, "en"
        )

    return response_text


async def _generate_sms_response(
    db: AsyncSession,
    english_text: str,
    sender_language: str,
) -> str:
    """Generate an AI response for the SMS using Gemini."""
    try:
        from google import genai
        from google.genai import types

        if not settings.gemini_api_key:
            raise ValueError("No Gemini API key")

        client = genai.Client(api_key=settings.gemini_api_key)

        # Get departments for context
        result = await db.execute(
            select(Department).where(Department.is_active.is_(True))
        )
        departments = result.scalars().all()
        dept_info = "\n".join(
            f"- {d.name} (ID: {d.id}): {d.description or 'N/A'}"
            for d in departments
        )

        lang_name = LANGUAGE_NAMES.get(sender_language, sender_language)
        system_prompt = SMS_SYSTEM_PROMPT.format(
            office_name=settings.office_name,
            current_time=datetime.now().strftime("%A, %B %d, %Y at %I:%M %p"),
            sender_language=lang_name,
            departments_info=dept_info or "No departments configured.",
        )

        response = await client.aio.models.generate_content(
            model=settings.gemini_model,
            contents=english_text,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=settings.gemini_temperature,
                max_output_tokens=160,  # SMS-appropriate length
            ),
        )

        return response.text or _fallback_sms()
    except BaseException:
        logger.exception("SMS AI response generation failed")
        return _fallback_sms()


def _fallback_sms() -> str:
    return (
        f"Thank you for contacting {settings.office_name}. "
        "We're experiencing technical issues. Please call us directly for assistance."
    )
