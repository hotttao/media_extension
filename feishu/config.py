from __future__ import annotations

import os
import pathlib


ROOT_ENV_PATH = pathlib.Path(__file__).resolve().parent.parent / ".env"


def _parse_env_file(path: pathlib.Path) -> dict[str, str]:
    if not path.exists():
        return {}

    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key] = value
    return values


_ENV = _parse_env_file(ROOT_ENV_PATH)


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name) or _ENV.get(name, default)


def _env_bool(name: str, default: bool) -> bool:
    value = _env(name, str(default)).strip().lower()
    return value in {"1", "true", "yes", "on"}


NOTIFICATION_CHANNELS = {
    "feishu": {
        "enabled": _env_bool("FEISHU_ENABLED", True),
        "app_id": _env("FEISHU_APP_ID"),
        "app_secret": _env("FEISHU_APP_SECRET"),
        "receive_id": _env("FEISHU_RECEIVE_ID"),
        "receive_id_type": _env("FEISHU_RECEIVE_ID_TYPE", "chat_id"),
    },
    "wechat": {
        "enabled": _env_bool("WECHAT_ENABLED", False),
        "webhook_url": _env("WECHAT_WEBHOOK_URL"),
    },
}
