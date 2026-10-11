"""Model catalog — every popular model, grouped by provider, with the transports
each supports and the key env var the API transport reads. Drives the Settings
picker; adding a credential here is what makes an agent runnable."""

from __future__ import annotations

# transport options per model: 'api' (key), 'subscription' (headless CLI), 'local' (ollama/vllm)
CATALOG = [
    {"provider": "Anthropic", "key_env": "ANTHROPIC_API_KEY", "cli": "claude", "models": [
        {"id": "claude-opus-4-8", "label": "Claude Opus 4.8", "transports": ["api", "subscription"]},
        {"id": "claude-sonnet-4.6", "label": "Claude Sonnet 4.6", "transports": ["api", "subscription"]},
        {"id": "claude-haiku-4.5", "label": "Claude Haiku 4.5", "transports": ["api", "subscription"]},
    ]},
    {"provider": "OpenAI", "key_env": "OPENAI_API_KEY", "cli": "codex", "models": [
        {"id": "gpt-5.1", "label": "GPT-5.1", "transports": ["api", "subscription"]},
        {"id": "gpt-5", "label": "GPT-5", "transports": ["api", "subscription"]},
        {"id": "gpt-4.1", "label": "GPT-4.1", "transports": ["api"]},
        {"id": "o4-mini", "label": "o4-mini", "transports": ["api"]},
    ]},
    {"provider": "Google", "key_env": "GEMINI_API_KEY", "cli": "gemini", "models": [
        {"id": "gemini-3-pro", "label": "Gemini 3 Pro", "transports": ["api", "subscription"]},
        {"id": "gemini-2.5-flash", "label": "Gemini 2.5 Flash", "transports": ["api", "subscription"]},
    ]},
    {"provider": "DeepSeek", "key_env": "DEEPSEEK_API_KEY", "models": [
        {"id": "deepseek-v3.2", "label": "DeepSeek V3.2", "transports": ["api", "local"]},
        {"id": "deepseek-r1", "label": "DeepSeek R1", "transports": ["api", "local"]},
    ]},
    {"provider": "Moonshot", "key_env": "MOONSHOT_API_KEY", "models": [
        {"id": "kimi-k2", "label": "Kimi K2", "transports": ["api"]},
    ]},
    {"provider": "xAI", "key_env": "XAI_API_KEY", "models": [
        {"id": "grok-4", "label": "Grok 4", "transports": ["api"]},
        {"id": "grok-3", "label": "Grok 3", "transports": ["api"]},
    ]},
    {"provider": "Meta", "key_env": "TOGETHER_API_KEY", "models": [
        {"id": "llama-4-maverick", "label": "Llama 4 Maverick", "transports": ["api", "local"]},
        {"id": "llama-3.3-70b", "label": "Llama 3.3 70B", "transports": ["api", "local"]},
    ]},
    {"provider": "Mistral", "key_env": "MISTRAL_API_KEY", "models": [
        {"id": "mistral-large", "label": "Mistral Large", "transports": ["api", "local"]},
        {"id": "codestral", "label": "Codestral", "transports": ["api", "local"]},
    ]},
    {"provider": "Alibaba", "key_env": "DASHSCOPE_API_KEY", "models": [
        {"id": "qwen3-72b", "label": "Qwen3 72B", "transports": ["api", "local"]},
        {"id": "qwen3-4b", "label": "Qwen3 4B", "transports": ["local"]},
        {"id": "qwen3-coder", "label": "Qwen3 Coder", "transports": ["api", "local"]},
    ]},
    {"provider": "Local (Ollama / vLLM)", "key_env": None, "models": [
        {"id": "llama3.1:8b", "label": "Llama 3.1 8B (local)", "transports": ["local"]},
        {"id": "qwen2.5-coder:7b", "label": "Qwen2.5 Coder 7B (local)", "transports": ["local"]},
        {"id": "bge-m3", "label": "BGE-M3 embeddings (local)", "transports": ["local"]},
    ]},
]

# default role → transport hint the roster uses when a model is added
ROLE_HINTS = ["orchestrator", "senior-dev", "frontend", "security", "security-analyst", "reflection", "devops"]

_BY_ID = {m["id"]: {**m, "provider": g["provider"], "key_env": g.get("key_env")}
          for g in CATALOG for m in g["models"]}


def model_info(model_id: str) -> dict | None:
    return _BY_ID.get(model_id)


def all_model_ids() -> list[str]:
    return list(_BY_ID)
