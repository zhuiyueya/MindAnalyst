
import os
import yaml
from typing import Dict, Any, Optional
from jinja2 import Template
import logging

logger = logging.getLogger(__name__)

class PromptManager:
    _instance = None
    _templates: Dict[str, Any] = {}
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(PromptManager, cls).__new__(cls)
            cls._instance._load_templates()
        return cls._instance
    
    def _load_templates(self):
        """Load all YAML templates from src/prompts/templates"""
        base_dir = os.path.dirname(os.path.abspath(__file__))
        templates_dir = os.path.join(base_dir, "templates")
        
        if not os.path.exists(templates_dir):
            logger.warning(f"Templates directory not found: {templates_dir}")
            return

        for root, _, files in os.walk(templates_dir):
            for file in files:
                if file.endswith((".yaml", ".yml")):
                    # Rel path as key: e.g. "video_summary/v1"
                    rel_dir = os.path.relpath(root, templates_dir)
                    name = os.path.splitext(file)[0]
                    key = f"{rel_dir}/{name}" if rel_dir != "." else name
                    
                    path = os.path.join(root, file)
                    try:
                        with open(path, 'r', encoding='utf-8') as f:
                            data = yaml.safe_load(f)
                            self._templates[key] = data
                    except Exception as e:
                        logger.error(f"Failed to load prompt template {path}: {e}")

    def get_prompt(self, template_key: str, **kwargs) -> Dict[str, str]:
        """
        Get rendered system and user prompts.
        Returns: {"system": "...", "user": "..."}
        """
        template = self._templates.get(template_key)
        if not template:
            logger.error(f"Template not found: {template_key}")
            return {"system": "", "user": ""}
            
        system_tmpl = Template(template.get("system", ""))
        user_tmpl = Template(template.get("user", ""))
        
        return {
            "system": system_tmpl.render(**kwargs),
            "user": user_tmpl.render(**kwargs)
        }

    def reload(self):
        self._templates = {}
        self._load_templates()
