import os


def _int_env(
    name: str,
    default: int
) -> int:

    raw = os.getenv(
        name
    )

    if raw is None or raw == "":

        return default

    try:

        return int(raw)

    except ValueError:

        return default


class Settings:

    OLLAMA_URL = os.getenv(
        "OLLAMA_URL",
        "http://host.docker.internal:11434"
    )

    OLLAMA_MODEL = os.getenv(
        "OLLAMA_MODEL",
        "gemma4:12b"
    )

    OLLAMA_MAX_ATTEMPTS = _int_env(
        "OLLAMA_MAX_ATTEMPTS",
        3
    )

    COMFYUI_URL = os.getenv(
        "COMFYUI_URL",
        "http://comfyui:8188"
    )

    COMFYUI_CHECKPOINT = os.getenv(
        "COMFYUI_CHECKPOINT",
        "sd_xl_base_1.0.safetensors"
    )

    COMFYUI_MAX_WAIT_SECONDS = _int_env(
        "COMFYUI_MAX_WAIT_SECONDS",
        1200
    )

    OUTPUT_DIR = os.getenv(
        "OUTPUT_DIR",
        "/app/output"
    )

    PROJECTS_DIR = os.getenv(
        "PROJECTS_DIR",
        "/app/projects"
    )

    TASKS_DIR = os.getenv(
        "TASKS_DIR",
        "/app/tasks"
    )

    TASK_TTL_SECONDS = _int_env(
        "TASK_TTL_SECONDS",
        1800
    )

    MAX_QUEUED_PER_KIND = _int_env(
        "MAX_QUEUED_PER_KIND",
        2
    )

    PROJECT_RETENTION_SECONDS = _int_env(
        "PROJECT_RETENTION_SECONDS",
        2592000
    )

    CLEANUP_INTERVAL_SECONDS = _int_env(
        "CLEANUP_INTERVAL_SECONDS",
        3600
    )


settings = Settings()
