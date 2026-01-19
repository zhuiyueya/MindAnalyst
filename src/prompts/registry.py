import os
import yaml
from typing import Any, Dict, Optional
import logging

logger = logging.getLogger(__name__)


class PromptRegistry:
    """Load prompt profile registry and resolve prompt keys by task/content type."""

    def __init__(self, profiles_path: Optional[str] = None):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        self.profiles_path = profiles_path or os.path.join(base_dir, "profiles.yaml")
        self._profiles: Dict[str, Any] = {}
        self._load_profiles()

    def _load_profiles(self) -> None:
        if not os.path.exists(self.profiles_path):
            logger.warning(f"Prompt profiles not found: {self.profiles_path}")
            self._profiles = {}
            return
        try:
            with open(self.profiles_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
                self._profiles = data.get("profiles", {}) if isinstance(data, dict) else {}
        except Exception as exc:
            logger.error(f"Failed to load prompt profiles: {exc}")
            self._profiles = {}

    def reload(self) -> None:
        self._load_profiles()

    def _extract_key(self, value: Any) -> Optional[str]:
        if not value:
            return None
        if isinstance(value, str):
            return value
        if isinstance(value, dict):
            key = value.get("key")
            return key if isinstance(key, str) else None
        return None

    def get_prompt_key(self, task_type: str, content_type: Optional[str], require_override: bool) -> Optional[str]:
        overrides = self._profiles.get("overrides", {}) if isinstance(self._profiles, dict) else {}
        common = self._profiles.get("common", {}) if isinstance(self._profiles, dict) else {}
        content_type = content_type or "generic"

        if require_override:
            override_block = overrides.get(content_type, {})
            key = self._extract_key(override_block.get(task_type))
            if key:
                return key
            fallback_block = overrides.get("generic", {})
            return self._extract_key(fallback_block.get(task_type))

        return self._extract_key(common.get(task_type))
