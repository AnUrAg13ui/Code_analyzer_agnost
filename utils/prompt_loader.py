"""
Prompt loader utility.
Loads SYSTEM_PROMPT and FINDING_SCHEMA from YAML files in config/prompts/.
Caches results so each file is read only once per process lifetime.
"""

import pathlib
import logging
from functools import lru_cache
from typing import Tuple

import yaml

logger = logging.getLogger(__name__)

PROMPTS_DIR = pathlib.Path(__file__).parent.parent / "config" / "prompts"


@lru_cache(maxsize=None)
def load_prompt(agent_name: str) -> Tuple[str, str]:
    """
    Load and cache the system_prompt and finding_schema for a given agent.

    Args:
        agent_name: Base name of the YAML file (without extension), e.g. 'bug_detector'

    Returns:
        Tuple of (system_prompt: str, finding_schema: str)
    """
    yaml_path = PROMPTS_DIR / f"{agent_name}.yaml"

    if not yaml_path.exists():
        raise FileNotFoundError(
            f"Prompt YAML not found: {yaml_path}. "
            f"Expected file at config/prompts/{agent_name}.yaml"
        )

    with open(yaml_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    system_prompt = data.get("system_prompt", "").strip()
    finding_schema = data.get("finding_schema", "").strip()

    if not system_prompt:
        logger.warning("system_prompt is empty in %s", yaml_path)
    if not finding_schema:
        logger.warning("finding_schema is empty in %s", yaml_path)

    logger.debug("Loaded prompts for agent '%s' from %s", agent_name, yaml_path)
    return system_prompt, finding_schema
