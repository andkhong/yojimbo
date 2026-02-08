"""AI agent service: manages conversation with Google Gemini and function-calling."""

import json
import logging
from datetime import date, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.constants import LANGUAGE_NAMES
from app.core.prompts import (
    RECEPTIONIST_SYSTEM_PROMPT,
    get_gemini_function_declarations,
)
from app.services import appointment_engine

logger = logging.getLogger(__name__)

_gemini_client = None


def _get_gemini_client():
    global _gemini_client
    if _gemini_client is not None:
        return _gemini_client
    if not settings.gemini_api_key:
        return None
    try:
        from google import genai

        _gemini_client = genai.Client(api_key=settings.gemini_api_key)
        return _gemini_client
    except Exception:
        logger.warning("Google Gemini client not available")
        return None


class ConversationSession:
    """Holds the state for a single call conversation with Gemini."""

    def __init__(
        self,
        call_sid: str,
        caller_phone: str,
        caller_language: str = "en",
        departments: list[dict] | None = None,
    ):
        self.call_sid = call_sid
        self.caller_phone = caller_phone
        self.caller_language = caller_language
        self.departments = departments or []
        self.history: list[dict] = []
        self.turn_count = 0
        self._chat_session = None

        # Build the system instruction
        dept_info = "\n".join(
            f"- {d['name']} (ID: {d['id']}): {d.get('description', 'N/A')}. "
            f"Hours: {d.get('operating_hours', 'Mon-Fri 9am-5pm')}"
            for d in self.departments
        )
        lang_name = LANGUAGE_NAMES.get(caller_language, caller_language)

        self.system_instruction = RECEPTIONIST_SYSTEM_PROMPT.format(
            office_name=settings.office_name,
            current_time=datetime.now().strftime("%A, %B %d, %Y at %I:%M %p"),
            caller_language=lang_name,
            departments_info=dept_info or "No departments configured.",
        )

    def _get_tools(self):
        """Build Gemini tools configuration."""
        from google.genai import types

        return types.Tool(
            function_declarations=[
                types.FunctionDeclaration(**fd)
                for fd in get_gemini_function_declarations()
            ]
        )

    def _get_config(self):
        """Build Gemini generation config."""
        from google.genai import types

        return types.GenerateContentConfig(
            system_instruction=self.system_instruction,
            temperature=settings.gemini_temperature,
            max_output_tokens=settings.gemini_max_tokens,
            tools=[self._get_tools()],
        )

    async def process_caller_input(
        self,
        text: str,
        db: AsyncSession,
    ) -> str:
        """Process caller speech and return the agent's response text."""
        self.turn_count += 1

        client = _get_gemini_client()
        if client is None:
            return self._fallback_response(text)

        try:
            from google.genai import types

            # Build the conversation contents
            contents = []
            for entry in self.history:
                contents.append(
                    types.Content(
                        role=entry["role"],
                        parts=[types.Part.from_text(text=entry["text"])]
                        if "text" in entry
                        else entry["parts"],
                    )
                )
            # Add the new user message
            contents.append(
                types.Content(
                    role="user",
                    parts=[types.Part.from_text(text=text)],
                )
            )

            response = await client.aio.models.generate_content(
                model=settings.gemini_model,
                contents=contents,
                config=self._get_config(),
            )

            # Handle function calls (Gemini may return one or more)
            if response.candidates and response.candidates[0].content.parts:
                parts = response.candidates[0].content.parts
                function_calls = [p for p in parts if p.function_call]

                if function_calls:
                    # Store model response with function calls in history
                    self.history.append({"role": "user", "text": text})
                    self.history.append({
                        "role": "model",
                        "parts": parts,
                    })

                    # Execute each function call and collect results
                    function_response_parts = []
                    for fc_part in function_calls:
                        fn_name = fc_part.function_call.name
                        fn_args = dict(fc_part.function_call.args) if fc_part.function_call.args else {}
                        fn_result = await self._execute_function(fn_name, fn_args, db)

                        function_response_parts.append(
                            types.Part.from_function_response(
                                name=fn_name,
                                response=fn_result,
                            )
                        )

                    # Send function results back to Gemini
                    contents.append(
                        types.Content(role="model", parts=parts)
                    )
                    contents.append(
                        types.Content(role="user", parts=function_response_parts)
                    )

                    follow_up = await client.aio.models.generate_content(
                        model=settings.gemini_model,
                        contents=contents,
                        config=self._get_config(),
                    )

                    assistant_text = follow_up.text or ""

                    self.history.append({
                        "role": "user",
                        "parts": function_response_parts,
                    })
                    self.history.append({"role": "model", "text": assistant_text})

                    return assistant_text
                else:
                    # Normal text response
                    assistant_text = response.text or ""
                    self.history.append({"role": "user", "text": text})
                    self.history.append({"role": "model", "text": assistant_text})
                    return assistant_text
            else:
                assistant_text = response.text or self._fallback_response(text)
                self.history.append({"role": "user", "text": text})
                self.history.append({"role": "model", "text": assistant_text})
                return assistant_text

        except Exception:
            logger.exception("Gemini API call failed")
            return self._fallback_response(text)

    async def _execute_function(
        self, fn_name: str, fn_args: dict, db: AsyncSession
    ) -> dict:
        """Execute an AI function call and return the result."""
        try:
            if fn_name == "check_availability":
                target_date = date.fromisoformat(str(fn_args["date"]))
                dept_id = int(fn_args["department_id"])
                slots = await appointment_engine.get_available_slots(
                    db, dept_id, target_date
                )
                return {"available_slots": slots, "count": len(slots)}

            elif fn_name == "book_appointment":
                contact = await appointment_engine.get_or_create_contact(
                    db,
                    self.caller_phone,
                    str(fn_args.get("contact_name", "")),
                    self.caller_language,
                )
                appt_date = date.fromisoformat(str(fn_args["date"]))
                hour, minute = map(int, str(fn_args["time"]).split(":"))
                start = datetime.combine(
                    appt_date,
                    datetime.min.time().replace(hour=hour, minute=minute),
                )
                end = start + timedelta(minutes=30)

                appt = await appointment_engine.book_appointment(
                    db,
                    contact_id=contact.id,
                    department_id=int(fn_args["department_id"]),
                    scheduled_start=start,
                    scheduled_end=end,
                    title=str(fn_args["purpose"]),
                    language=self.caller_language,
                )
                return {
                    "success": True,
                    "appointment_id": appt.id,
                    "date": str(fn_args["date"]),
                    "time": str(fn_args["time"]),
                    "department_id": int(fn_args["department_id"]),
                }

            elif fn_name == "lookup_appointment":
                phone = str(fn_args.get("phone_number", self.caller_phone))
                appointments = await appointment_engine.lookup_appointments_by_phone(
                    db, phone
                )
                return {
                    "appointments": [
                        {
                            "id": a.id,
                            "title": a.title,
                            "date": a.scheduled_start.strftime("%Y-%m-%d"),
                            "time": a.scheduled_start.strftime("%H:%M"),
                            "status": a.status,
                            "department_id": a.department_id,
                        }
                        for a in appointments
                    ]
                }

            elif fn_name == "cancel_appointment":
                appt = await appointment_engine.cancel_appointment(
                    db,
                    int(fn_args["appointment_id"]),
                    str(fn_args.get("reason", "")),
                )
                if appt:
                    return {"success": True, "appointment_id": appt.id}
                return {"success": False, "error": "Appointment not found"}

            elif fn_name == "transfer_call":
                return {
                    "action": "transfer",
                    "department_id": int(fn_args["department_id"]),
                    "reason": str(fn_args.get("reason", "")),
                }

            elif fn_name == "send_confirmation_sms":
                return {
                    "success": True,
                    "message": "SMS confirmation sent",
                    "to": str(fn_args["phone_number"]),
                }

            else:
                return {"error": f"Unknown function: {fn_name}"}

        except Exception:
            logger.exception("Function execution failed: %s", fn_name)
            return {"error": f"Failed to execute {fn_name}"}

    def _fallback_response(self, text: str) -> str:
        """Fallback response when Gemini is unavailable."""
        return (
            "I apologize, but I'm experiencing technical difficulties. "
            "Please hold while I transfer you to a staff member, "
            "or call back in a few minutes."
        )

    def get_summary_prompt(self) -> str:
        """Return a prompt for generating a call summary."""
        return (
            "Based on the conversation above, provide a brief 1-2 sentence summary "
            "of what the caller needed and the outcome. Also classify the caller's "
            "sentiment as positive, neutral, or negative."
        )
