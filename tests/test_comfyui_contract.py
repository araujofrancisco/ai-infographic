import json
from pathlib import Path

from comfyui_client import ComfyUIClient
from config import settings

WORKFLOW_PATH = (
    Path(__file__).resolve().parent.parent
    / "app"
    / "workflows"
    / "illustration_api.json"
)

EXPECTED_TYPES = {
    ComfyUIClient.CHECKPOINT_NODE: "CheckpointLoaderSimple",
    ComfyUIClient.POSITIVE_PROMPT_NODE: "CLIPTextEncode",
    ComfyUIClient.NEGATIVE_PROMPT_NODE: "CLIPTextEncode",
    ComfyUIClient.KSAMPLER_NODE: "KSampler",
    ComfyUIClient.LATENT_NODE: "EmptyLatentImage",
    ComfyUIClient.SAVE_IMAGE_NODE: "SaveImage"
}


def load_workflow() -> dict:

    return json.loads(
        WORKFLOW_PATH.read_text(
            encoding="utf-8"
        )
    )


def test_workflow_node_ids_match_expected_types():

    workflow = load_workflow()

    for node_id, expected_type in EXPECTED_TYPES.items():

        assert node_id in workflow, (
            f"workflow is missing node {node_id}"
        )

        assert (
            workflow[node_id]["class_type"]
            == expected_type
        ), (
            f"node {node_id} is not a {expected_type}"
        )


def test_ksampler_wiring():

    workflow = load_workflow()

    ksampler = workflow[
        ComfyUIClient.KSAMPLER_NODE
    ]["inputs"]

    assert ksampler["positive"] == [
        ComfyUIClient.POSITIVE_PROMPT_NODE,
        0
    ]

    assert ksampler["negative"] == [
        ComfyUIClient.NEGATIVE_PROMPT_NODE,
        0
    ]

    assert ksampler["latent_image"] == [
        ComfyUIClient.LATENT_NODE,
        0
    ]

    assert ksampler["model"] == [
        ComfyUIClient.CHECKPOINT_NODE,
        0
    ]


def test_prompt_nodes_receive_checkpoint_clip():

    workflow = load_workflow()

    for node_id in [
        ComfyUIClient.POSITIVE_PROMPT_NODE,
        ComfyUIClient.NEGATIVE_PROMPT_NODE
    ]:

        assert (
            workflow[node_id]["inputs"]["clip"]
            == [
                ComfyUIClient.CHECKPOINT_NODE,
                1
            ]
        )


def test_save_image_receives_decoded_latent():

    workflow = load_workflow()

    assert (
        workflow[
            ComfyUIClient.SAVE_IMAGE_NODE
        ]["inputs"]["images"]
        == [
            "11",
            0
        ]
    )


def test_build_workflow_injects_values():

    client = ComfyUIClient()

    workflow = client.build_workflow(
        prompt="positive",
        negative_prompt="negative",
        seed=42
    )

    assert (
        workflow[
            ComfyUIClient.CHECKPOINT_NODE
        ]["inputs"]["ckpt_name"]
        == settings.COMFYUI_CHECKPOINT
    )

    assert (
        workflow[
            ComfyUIClient.POSITIVE_PROMPT_NODE
        ]["inputs"]["text"]
        == "positive"
    )

    assert (
        workflow[
            ComfyUIClient.NEGATIVE_PROMPT_NODE
        ]["inputs"]["text"]
        == "negative"
    )

    assert (
        workflow[
            ComfyUIClient.KSAMPLER_NODE
        ]["inputs"]["seed"]
        == 42
    )

    assert (
        workflow[
            ComfyUIClient.LATENT_NODE
        ]["inputs"]["width"]
        == ComfyUIClient.IMAGE_WIDTH
    )

    assert (
        workflow[
            ComfyUIClient.LATENT_NODE
        ]["inputs"]["height"]
        == ComfyUIClient.IMAGE_HEIGHT
    )

    assert (
        workflow[
            ComfyUIClient.SAVE_IMAGE_NODE
        ]["inputs"]["filename_prefix"]
        == ComfyUIClient.FILENAME_PREFIX
    )


def test_build_workflow_uses_configured_checkpoint(
    monkeypatch
):

    monkeypatch.setattr(
        settings,
        "COMFYUI_CHECKPOINT",
        "custom_model.safetensors"
    )

    client = ComfyUIClient()

    workflow = client.build_workflow(
        prompt="p",
        negative_prompt="n",
        seed=1
    )

    assert (
        workflow[
            ComfyUIClient.CHECKPOINT_NODE
        ]["inputs"]["ckpt_name"]
        == "custom_model.safetensors"
    )


def test_build_workflow_does_not_mutate_source():

    client = ComfyUIClient()

    before = json.dumps(
        client.workflow,
        sort_keys=True
    )

    client.build_workflow(
        prompt="p",
        negative_prompt="n",
        seed=1
    )

    after = json.dumps(
        client.workflow,
        sort_keys=True
    )

    assert before == after
