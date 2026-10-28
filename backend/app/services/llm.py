"""Local Ollama and optional OpenAI-compatible structured JSON adapters."""
import json
import os
from typing import TypeVar
import httpx
import yaml
from pydantic import BaseModel
from ..core.config import settings, ROOT
T = TypeVar("T", bound=BaseModel)

def strict_schema(schema: dict) -> dict:
    """Require all object properties for strict compatible APIs, including defaults."""
    import copy
    result = copy.deepcopy(schema)
    def visit(node: object) -> None:
        """Recursively make nested JSON Schema object shapes strict."""
        if isinstance(node, dict):
            if node.get("type") == "object":
                node["additionalProperties"] = False
                node["required"] = list(node.get("properties", {}))
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for value in node:
                visit(value)
    visit(result)
    return result

def role_config(role: str) -> dict:
    """Resolve role settings without exporting secrets into run metadata."""
    config = getattr(settings.agents, role)
    return {"provider": config.provider or settings.llm_provider, "model": config.model or settings.llm_model,
            "url": config.url or settings.llm_url, "api_key": os.environ.get(config.api_key_env, "") if config.api_key_env else settings.api_key,
            "timeout": config.timeout_seconds}

def structured(stage: str, data: dict, schema: type[T]) -> T:
    """Validate a model JSON response against a strict schema; failures never fall back silently."""
    template = yaml.safe_load((ROOT / "configs/prompts" / f"{stage}.yaml").read_text(encoding="utf-8"))
    config = role_config({"summary": "summary", "entity_relation": "extractor", "review": "reviewer"}[stage])
    messages = [{"role": "system", "content": template["system"]}, {"role": "user", "content": json.dumps(data, ensure_ascii=False)}]
    with httpx.Client(timeout=config["timeout"], trust_env=False) as client:
        if config["provider"] == "ollama":
            response = client.post(config["url"].rstrip("/") + "/api/chat", json={"model": config["model"], "messages": messages, "stream": False, "format": schema.model_json_schema(), "options": {"temperature": 0, "seed": 42}})
            response.raise_for_status()
            content = response.json()["message"]["content"]
        elif config["provider"] == "openai":
            response = client.post(config["url"].rstrip("/") + "/chat/completions", headers={"Authorization": f"Bearer {config['api_key']}"}, json={"model": config["model"], "temperature": 0, "messages": messages, "response_format": {"type": "json_schema", "json_schema": {"name": stage, "strict": True, "schema": strict_schema(schema.model_json_schema())}}})
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
        else:
            raise ValueError("Demo provider does not make LLM requests")
    return schema.model_validate_json(content)
