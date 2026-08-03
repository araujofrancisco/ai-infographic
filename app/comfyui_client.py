import asyncio
import copy
import json
import random
import time
from pathlib import Path

import httpx

from config import settings
from exceptions import GenerationError


class ComfyUIClient:

    CHECKPOINT_NODE = "1"
    POSITIVE_PROMPT_NODE = "3"
    NEGATIVE_PROMPT_NODE = "4"
    KSAMPLER_NODE = "5"
    LATENT_NODE = "9"
    SAVE_IMAGE_NODE = "13"

    FILENAME_PREFIX = "infographic_illustration"

    IMAGE_WIDTH = 1024
    IMAGE_HEIGHT = 1448

    def __init__(self):

        self.base_url = settings.COMFYUI_URL.rstrip("/")

        workflow_path = (
            Path(__file__).parent
            / "workflows"
            / "illustration_api.json"
        )

        if not workflow_path.exists():

            raise FileNotFoundError(
                f"ComfyUI workflow not found: "
                f"{workflow_path}"
            )

        with open(
            workflow_path,
            "r",
            encoding="utf-8"
        ) as file:

            self.workflow = json.load(file)

    def build_workflow(
        self,
        prompt: str,
        negative_prompt: str,
        seed: int | None = None
    ):

        workflow = copy.deepcopy(
            self.workflow
        )

        if seed is None:

            seed = random.randint(
                0,
                2**63 - 1
            )

        workflow[
            self.POSITIVE_PROMPT_NODE
        ]["inputs"]["text"] = prompt

        workflow[
            self.NEGATIVE_PROMPT_NODE
        ]["inputs"]["text"] = negative_prompt

        workflow[
            self.KSAMPLER_NODE
        ]["inputs"]["seed"] = seed

        workflow[
            self.SAVE_IMAGE_NODE
        ]["inputs"]["filename_prefix"] = (
            self.FILENAME_PREFIX
        )

        workflow[
            self.LATENT_NODE
        ]["inputs"]["width"] = (
            self.IMAGE_WIDTH
        )

        workflow[
            self.LATENT_NODE
        ]["inputs"]["height"] = (
            self.IMAGE_HEIGHT
        )

        return workflow

    async def generate_image(
        self,
        prompt: str,
        negative_prompt: str,
        output_path: str,
        seed: int | None = None
    ):

        workflow = self.build_workflow(
            prompt=prompt,
            negative_prompt=negative_prompt,
            seed=seed
        )

        payload = {
            "prompt": workflow
        }

        # Image generation can run for minutes,
        # so no client-side timeout is applied here.
        async with httpx.AsyncClient(
            timeout=None
        ) as client:

            response = await self._post_prompt(
                client=client,
                payload=payload
            )

            prompt_id = response["prompt_id"]

            history = await self._wait_for_completion(
                client=client,
                prompt_id=prompt_id
            )

            image_info = self._find_output_image(
                history
            )

            if image_info is None:

                raise GenerationError(
                    "ComfyUI completed the workflow "
                    "but no output image was found."
                )

            image_data = await self._download_image(
                client=client,
                image_info=image_info
            )

        output_file = Path(
            output_path
        )

        output_file.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        output_file.write_bytes(
            image_data
        )

        return str(
            output_file
        )

    async def _post_prompt(
        self,
        client: httpx.AsyncClient,
        payload: dict
    ):

        try:

            response = await client.post(
                f"{self.base_url}/prompt",
                json=payload
            )

        except httpx.HTTPError as exc:

            raise GenerationError(
                f"Cannot reach ComfyUI at {self.base_url}: {exc}"
            )

        if response.is_error:

            detail = self._error_detail(
                response
            )

            raise GenerationError(
                f"ComfyUI rejected the workflow "
                f"({response.status_code}): {detail}"
            )

        return response.json()

    def _error_detail(
        self,
        response: httpx.Response
    ) -> str:

        try:

            body = response.json()

            detail = body.get(
                "error",
                {}
            )

            message = detail.get(
                "message",
                ""
            )

            if message:

                return message

        except (ValueError, AttributeError):

            pass

        return response.text.strip()[:500]

    async def _wait_for_completion(
        self,
        client: httpx.AsyncClient,
        prompt_id: str
    ):

        deadline = (
            time.monotonic()
            + settings.COMFYUI_MAX_WAIT_SECONDS
        )

        while True:

            remaining = (
                deadline
                - time.monotonic()
            )

            if remaining <= 0:

                raise GenerationError(
                    "ComfyUI did not finish the workflow "
                    f"within {settings.COMFYUI_MAX_WAIT_SECONDS} "
                    "seconds."
                )

            try:

                response = await client.get(
                    f"{self.base_url}/history/{prompt_id}"
                )

            except httpx.HTTPError as exc:

                raise GenerationError(
                    "Lost connection to ComfyUI while "
                    f"waiting for the workflow: {exc}"
                ) from exc

            if response.is_error:

                raise GenerationError(
                    "ComfyUI history request failed "
                    f"({response.status_code})."
                )

            history = response.json()

            if prompt_id in history:

                entry = history[prompt_id]

                status = entry.get(
                    "status",
                    {}
                )

                status_string = status.get(
                    "status_str"
                )

                if status_string == "error":

                    raise GenerationError(
                        self._status_error(
                            status
                        )
                    )

                if status.get(
                    "completed",
                    False
                ):

                    return entry

            await asyncio.sleep(1)

    def _status_error(
        self,
        status: dict
    ) -> str:

        details = []

        for message in status.get(
            "messages",
            []
        ):

            if message.get(
                "type"
            ) not in (
                "execution_error",
                "execution_interrupted"
            ):

                continue

            payload = message.get(
                "message",
                ""
            )

            if isinstance(
                payload,
                dict
            ):

                node_type = payload.get(
                    "node_type",
                    ""
                )

                error_text = payload.get(
                    "exception_message",
                    ""
                )

                if error_text:

                    details.append(
                        f"{node_type}: {error_text}"
                        if node_type
                        else str(
                            error_text
                        )
                    )

            elif payload:

                details.append(
                    str(
                        payload
                    )
                )

        if details:

            return (
                "ComfyUI workflow failed: "
                + " | ".join(
                    details[:3]
                )
            )

        return (
            "ComfyUI workflow failed."
        )

    def _find_output_image(
        self,
        history
    ):

        outputs = history.get(
            "outputs",
            {}
        )

        save_image_output = outputs.get(
            self.SAVE_IMAGE_NODE
        )

        if save_image_output:

            images = save_image_output.get(
                "images",
                []
            )

            if images:

                return images[0]

        for node_output in outputs.values():

            images = node_output.get(
                "images",
                []
            )

            if images:

                return images[0]

        return None

    async def _download_image(
        self,
        client: httpx.AsyncClient,
        image_info
    ):

        params = {
            "filename": image_info["filename"],
            "subfolder": image_info.get(
                "subfolder",
                ""
            ),
            "type": image_info.get(
                "type",
                "output"
            )
        }

        response = await client.get(
            f"{self.base_url}/view",
            params=params
        )

        response.raise_for_status()

        return response.content
