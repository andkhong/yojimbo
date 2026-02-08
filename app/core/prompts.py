RECEPTIONIST_SYSTEM_PROMPT = """You are Yojimbo, an AI receptionist for {office_name}. \
You are helpful, professional, and patient. You are handling a phone call.

Current date and time: {current_time}
Caller's detected language: {caller_language}

Available departments:
{departments_info}

You can perform these actions using function calls:
1. book_appointment - Schedule an appointment with a department
2. check_availability - Check available time slots for a department on a date
3. transfer_call - Transfer the caller to a specific department
4. lookup_appointment - Look up existing appointments for the caller
5. cancel_appointment - Cancel an existing appointment
6. send_confirmation_sms - Send an SMS confirmation to the caller

Guidelines:
- Be concise and natural. Phone conversations should be brief and clear.
- If the caller's request is unclear, ask ONE clarifying question at a time.
- Always confirm appointment details before booking.
- If you cannot help, offer to transfer to a human staff member.
- Never make up information about office hours, services, or availability.
- Respond in the caller's language ({caller_language}).
- When booking an appointment, always confirm: department, date, time, and purpose.
"""

SMS_SYSTEM_PROMPT = """You are Yojimbo, an AI assistant for {office_name}. \
You are responding to an SMS text message.

Current date and time: {current_time}
Sender's detected language: {sender_language}

Available departments:
{departments_info}

You can perform the same actions as phone calls (book_appointment, check_availability, etc.).

Guidelines:
- Keep responses concise (SMS-appropriate length).
- Respond in the sender's language.
- If the message is a simple confirmation (yes/no), handle it directly.
- Include relevant details like appointment times and department names.
"""


def get_gemini_function_declarations() -> list[dict]:
    """Return function declarations in Google Gemini's native format."""
    return [
        {
            "name": "book_appointment",
            "description": "Book an appointment with a government department",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "department_id": {
                        "type": "INTEGER",
                        "description": "The department ID to book with",
                    },
                    "date": {
                        "type": "STRING",
                        "description": "The appointment date in YYYY-MM-DD format",
                    },
                    "time": {
                        "type": "STRING",
                        "description": "The appointment time in HH:MM format (24-hour)",
                    },
                    "purpose": {
                        "type": "STRING",
                        "description": "Brief description of the appointment purpose",
                    },
                    "contact_name": {
                        "type": "STRING",
                        "description": "The caller's name",
                    },
                },
                "required": ["department_id", "date", "time", "purpose"],
            },
        },
        {
            "name": "check_availability",
            "description": "Check available appointment time slots for a department on a specific date",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "department_id": {
                        "type": "INTEGER",
                        "description": "The department ID to check",
                    },
                    "date": {
                        "type": "STRING",
                        "description": "The date to check in YYYY-MM-DD format",
                    },
                },
                "required": ["department_id", "date"],
            },
        },
        {
            "name": "transfer_call",
            "description": "Transfer the call to a specific department",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "department_id": {
                        "type": "INTEGER",
                        "description": "The department ID to transfer to",
                    },
                    "reason": {
                        "type": "STRING",
                        "description": "Reason for the transfer",
                    },
                },
                "required": ["department_id"],
            },
        },
        {
            "name": "lookup_appointment",
            "description": "Look up existing appointments for the caller",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "phone_number": {
                        "type": "STRING",
                        "description": "Caller's phone number in E.164 format",
                    },
                },
                "required": ["phone_number"],
            },
        },
        {
            "name": "cancel_appointment",
            "description": "Cancel an existing appointment",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "appointment_id": {
                        "type": "INTEGER",
                        "description": "The appointment ID to cancel",
                    },
                    "reason": {
                        "type": "STRING",
                        "description": "Reason for cancellation",
                    },
                },
                "required": ["appointment_id"],
            },
        },
        {
            "name": "send_confirmation_sms",
            "description": "Send an SMS confirmation message to the caller",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "phone_number": {
                        "type": "STRING",
                        "description": "Phone number to send SMS to",
                    },
                    "message": {
                        "type": "STRING",
                        "description": "The confirmation message to send",
                    },
                },
                "required": ["phone_number", "message"],
            },
        },
    ]
