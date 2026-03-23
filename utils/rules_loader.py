"""
Custom rules loader.
Reads user-defined rules from config/custom_rules.yaml and formats them
as a structured text block ready to be injected into the RulesChecker prompt.

Rules are cached after the first read. To hot-reload rules without restarting
the server, call clear_cache() and then load_custom_rules() again.
"""

import pathlib
import logging
from functools import lru_cache
from typing import List, Dict

import yaml

logger = logging.getLogger(__name__)

RULES_FILE = pathlib.Path(__file__).parent.parent / "config" / "custom_rules.yaml"


@lru_cache(maxsize=1)
def load_custom_rules() -> str:
    """
    Load rules from config/custom_rules.yaml and return them as a
    formatted text block ready for LLM injection.

    Returns:
        A formatted multi-line string listing all active rules,
        or an empty string if no rules file exists.
    """
    if not RULES_FILE.exists():
        logger.warning("custom_rules.yaml not found at %s — rules checker will use LLM defaults.", RULES_FILE)
        return ""

    with open(RULES_FILE, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    rules: List[Dict] = data.get("rules", [])
    if not rules:
        logger.info("custom_rules.yaml loaded but no rules defined.")
        return ""

    lines = ["The following project-specific rules MUST be enforced:\n"]
    for i, rule in enumerate(rules, 1):
        name = rule.get("name", f"rule-{i}")
        severity = rule.get("severity", "medium").upper()
        description = rule.get("description", "").strip()
        lines.append(f"  [{i}] [{severity}] {name}\n       → {description}\n")

    formatted = "\n".join(lines)
    logger.info("Loaded %d custom rules from %s", len(rules), RULES_FILE)
    return formatted


def clear_cache() -> None:
    """Call this to force a reload of rules from disk on the next request."""
    load_custom_rules.cache_clear()
    logger.info("Custom rules cache cleared — will reload from disk on next call.")
