import os


def _to_bool(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


USE_NEW_PIPELINE = _to_bool(os.getenv("USE_NEW_PIPELINE", "false"))
