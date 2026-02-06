import os
import yaml
import logging
from typing import Any, Dict, Optional
from src.core.config import settings

logger = logging.getLogger(__name__)


class ModelProviderRegistry:
    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path or settings.MODEL_CONFIG_PATH
        self.providers: Dict[str, Dict[str, Any]] = {}
        self.models: Dict[str, Dict[str, Any]] = {}
        self.scenes: Dict[str, str] = {}
        self._load_config()

    def _resolve_path(self, path: str) -> str:
        if os.path.isabs(path):
            return path
        base_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.abspath(os.path.join(base_dir, "..", ".."))
        return os.path.join(project_root, path)

    def _load_config(self) -> None:
        if not self.config_path:
            logger.warning("Model config path not set")
            return
        resolved = self._resolve_path(self.config_path)
        if not os.path.exists(resolved):
            logger.warning("Model config not found: %s", resolved)
            return
        try:
            with open(resolved, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        except Exception as exc:
            logger.error("Failed to load model config: %s", exc)
            return

        providers = data.get("providers", {}) if isinstance(data, dict) else {}
        self.providers = providers if isinstance(providers, dict) else {}

        self.models = {}
        for item in data.get("models", []) if isinstance(data, dict) else []:
            if not isinstance(item, dict):
                continue
            model_id = item.get("id")
            if isinstance(model_id, str):
                self.models[model_id] = item

        scenes = data.get("scenes", {}) if isinstance(data, dict) else {}
        self.scenes = scenes if isinstance(scenes, dict) else {}

    def get_scene_model_id(self, scene: str) -> Optional[str]:
        value = self.scenes.get(scene)
        return value if isinstance(value, str) else None

    def get_model_config(self, model_id: Optional[str]) -> Optional[Dict[str, Any]]:
        if not model_id:
            return None
        return self.models.get(model_id)

    def get_provider_config(self, provider_name: Optional[str]) -> Optional[Dict[str, Any]]:
        if not provider_name:
            return None
        return self.providers.get(provider_name)

    def reload(self) -> None:
        self.providers = {}
        self.models = {}
        self.scenes = {}
        self._load_config()
