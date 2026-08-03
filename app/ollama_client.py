import json
import logging
import httpx
from pydantic import ValidationError

from config import settings
from exceptions import GenerationError
from models import InfographicContent


logger = logging.getLogger(
    "infographic"
)


class OllamaClient:

    def __init__(self):

        self.base_url = settings.OLLAMA_URL.rstrip("/")
        self.model = settings.OLLAMA_MODEL
        self.max_attempts = settings.OLLAMA_MAX_ATTEMPTS

    async def generate_content(
        self,
        topic: str,
        audience: str,
        style: str,
        section_count: int
    ) -> InfographicContent:

        messages = [
            {
                "role": "system",
                "content": self._system_prompt(
                    audience=audience,
                    style=style,
                    section_count=section_count
                )
            },
            {
                "role": "user",
                "content": self._user_prompt(
                    topic
                )
            }
        ]

        for attempt in range(
            self.max_attempts
        ):

            raw = await self._chat(
                messages
            )

            try:

                parsed = json.loads(
                    raw
                )

            except (
                json.JSONDecodeError,
                TypeError
            ):

                if attempt == (
                    self.max_attempts - 1
                ):

                    raise GenerationError(
                        "Ollama returned invalid JSON: "
                        f"{self._trim(raw)}"
                    )

                logger.info(
                    "ollama invalid JSON on attempt %d/%d, retrying",
                    attempt + 1,
                    self.max_attempts
                )

                messages = self._corrective_messages(
                    messages,
                    raw,
                    f"invalid JSON: {self._trim(raw)}"
                )

                continue

            try:

                return InfographicContent.model_validate(
                    parsed
                )

            except ValidationError as exc:

                if attempt == (
                    self.max_attempts - 1
                ):

                    raise GenerationError(
                        "Ollama content does not match the "
                        f"expected schema: {self._trim(raw)}"
                    ) from exc

                logger.info(
                    "ollama schema mismatch on attempt %d/%d, retrying",
                    attempt + 1,
                    self.max_attempts
                )

                messages = self._corrective_messages(
                    messages,
                    raw,
                    f"schema mismatch: {exc}"
                )

        raise GenerationError(
            "Ollama did not return valid content."
        )

    def _system_prompt(
        self,
        audience: str,
        style: str,
        section_count: int
    ) -> str:

        return f"""
You are an expert educational infographic content designer.

Your job is to create concise, accurate content for an illustrated
educational cheat sheet.

The final output will be rendered as a professional infographic.

Rules:

1. Use concise text.
2. Do not write long paragraphs.
3. Each section must contain between 2 and 5 bullet points.
4. Each bullet point should be short enough to fit on an infographic.
5. Use technically accurate terminology.
6. Include practical examples when appropriate.
7. The visual_description must describe an illustration only.
8. Do not request text or labels inside illustrations.
9. Do not include Markdown.
10. Do not include HTML.
11. Do not include code fences.
12. Return only structured data matching the requested schema.

Target audience:
{audience}

Visual style:
{style}

Requested number of sections:
{section_count}
"""

    def _user_prompt(
        self,
        topic: str
    ) -> str:

        return f"""
Create an illustrated infographic cheat sheet about:

{topic}

The infographic should be useful for the target audience and should
organize the subject into logical sections.
"""

    def _corrective_messages(
        self,
        messages: list[dict],
        raw: str,
        reason: str
    ) -> list[dict]:

        return messages + [
            {
                "role": "assistant",
                "content": raw
            },
            {
                "role": "user",
                "content": (
                    "Your previous response was rejected.\n\n"
                    f"Reason: {reason}\n\n"
                    "Return ONLY valid JSON matching the requested "
                    "schema. No code fences, no markdown, no "
                    "commentary before or after the JSON. Keep all "
                    "fields exactly as specified. Previous output "
                    f"(truncated):\n{self._trim(raw)}"
                )
            }
        ]

    async def _chat(
        self,
        messages: list[dict]
    ) -> str:

        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "format": InfographicContent.model_json_schema(),
            "options": {
                "temperature": 0
            }
        }

        url = f"{self.base_url}/api/chat"

        try:

            async with httpx.AsyncClient(
                timeout=600
            ) as client:

                response = await client.post(
                    url,
                    json=payload
                )

                response.raise_for_status()

                data = response.json()

        except httpx.ConnectError as exc:

            raise GenerationError(
                f"Ollama is not reachable at "
                f"{self.base_url}: {exc}"
            ) from exc

        except httpx.TimeoutException as exc:

            raise GenerationError(
                "Ollama took longer than 10 minutes "
                f"and the request timed out: {exc}"
            ) from exc

        except httpx.HTTPError as exc:

            raise GenerationError(
                f"Ollama request failed: {exc}"
            ) from exc

        return data["message"]["content"]

    def _trim(
        self,
        text: str,
        limit: int = 500
    ) -> str:

        text = text.strip()

        if len(text) <= limit:

            return text

        return text[:limit] + "..."
