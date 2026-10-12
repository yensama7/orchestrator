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
    {"provider": "OpenRouter", "key_env": "OPENROUTER_API_KEY", "models": [
        # one key, any of these — and the Settings picker merges OpenRouter's full
        # live catalogue on top of this curated set (api/main.py get_catalog).
        {"id": "anthropic/claude-sonnet-4.5", "label": "Claude Sonnet 4.5 (OpenRouter)", "transports": ["api"]},
        {"id": "openai/gpt-5.1", "label": "GPT-5.1 (OpenRouter)", "transports": ["api"]},
        {"id": "google/gemini-2.5-pro", "label": "Gemini 2.5 Pro (OpenRouter)", "transports": ["api"]},
        {"id": "deepseek/deepseek-chat", "label": "DeepSeek V3 (OpenRouter)", "transports": ["api"]},
        {"id": "meta-llama/llama-3.3-70b-instruct", "label": "Llama 3.3 70B (OpenRouter)", "transports": ["api"]},
        {"id": "x-ai/grok-4", "label": "Grok 4 (OpenRouter)", "transports": ["api"]},
    ]},
    {"provider": "Local (Ollama / vLLM)", "key_env": None, "models": [
        {"id": "llama3.1:8b", "label": "Llama 3.1 8B (local)", "transports": ["local"]},
        {"id": "qwen2.5-coder:7b", "label": "Qwen2.5 Coder 7B (local)", "transports": ["local"]},
        {"id": "bge-m3", "label": "BGE-M3 embeddings (local)", "transports": ["local"]},
    ]},
]

# default role → transport hint the roster uses when a model is added
ROLE_HINTS = ["orchestrator", "senior-dev", "frontend", "security", "security-analyst", "reflection", "devops"]

# Starter role presets — a curated subset of the ECC agent library (github.com/
# affaan-m/ECC, MIT) mapped onto Lineage's role shape. The roster starts empty;
# these let a user one-click a proven role (skills + resources + a conservative
# egress allowlist) instead of waiting on the central agent to research one from
# scratch. `model_hint` is advisory for the picker — roles bind to models via
# agents, so it isn't persisted. Reviewers/analysts get egress=[] (analysis, no
# network); only roles that actually fetch get hosts.
ROLE_PRESETS = [
    {"name": "architect", "model_hint": "opus", "egress": [],
     "description": "System design, scalability, and technical trade-offs for new features and large refactors.",
     "skills": ["system design", "scalability analysis", "pattern selection", "trade-off evaluation", "bottleneck identification"],
     "resources": ["C4 model", "ADRs", "design patterns"]},
    {"name": "planner", "model_hint": "opus", "egress": [],
     "description": "Breaks complex features into ordered, dependency-aware implementation plans with risks and edge cases.",
     "skills": ["requirements analysis", "task decomposition", "dependency mapping", "risk identification", "sequencing"],
     "resources": ["issue tracker", "spec docs"]},
    {"name": "senior-dev", "model_hint": "sonnet", "egress": ["registry.npmjs.org", "pypi.org"],
     "description": "Implements features to spec, idiomatic and minimal-diff, reusing existing codebase patterns.",
     "skills": ["implementation", "refactoring", "pattern reuse", "API design", "incremental delivery"],
     "resources": ["standard library", "package registries"]},
    {"name": "code-reviewer", "model_hint": "sonnet", "egress": [],
     "description": "Reviews changes for quality, security, and maintainability; reports only high-confidence findings.",
     "skills": ["diff review", "security scanning", "maintainability check", "convention enforcement"],
     "resources": ["git diff", "linters"]},
    {"name": "security-reviewer", "model_hint": "sonnet", "egress": [],
     "description": "Detects OWASP Top 10, secrets, SSRF, injection, and unsafe crypto before code reaches production.",
     "skills": ["vulnerability detection", "secrets detection", "input-validation audit", "authz review", "dependency scanning"],
     "resources": ["OWASP Top 10", "CWE", "OSV"]},
    {"name": "tdd-guide", "model_hint": "sonnet", "egress": [],
     "description": "Enforces write-tests-first; targets 80%+ behavioral coverage for new features and bug fixes.",
     "skills": ["test-first workflow", "behavioral coverage", "edge-case design", "regression guarding"],
     "resources": ["test runner", "coverage tool"]},
    {"name": "python-reviewer", "model_hint": "sonnet", "egress": [],
     "description": "PEP 8, Pythonic idioms, type hints, security, and performance for Python changes.",
     "skills": ["PEP 8 review", "type-hint audit", "idiom check", "security review", "perf review"],
     "resources": ["ruff", "mypy"]},
    {"name": "typescript-reviewer", "model_hint": "sonnet", "egress": [],
     "description": "Type safety, async correctness, Node/web security, and idiomatic patterns for TS/JS.",
     "skills": ["type-safety audit", "async correctness", "security review", "idiom check"],
     "resources": ["tsc", "eslint"]},
    {"name": "react-reviewer", "model_hint": "sonnet", "egress": [],
     "description": "Hook correctness, render performance, server/client boundaries, and a11y for React components.",
     "skills": ["hook-rules audit", "render-perf review", "component-boundary check", "accessibility review"],
     "resources": ["React docs", "eslint-plugin-react-hooks"]},
    {"name": "database-reviewer", "model_hint": "sonnet", "egress": [],
     "description": "PostgreSQL query optimization, schema design, migration safety, and security.",
     "skills": ["query optimization", "schema design", "index review", "migration-safety check"],
     "resources": ["EXPLAIN ANALYZE", "pg_stat_statements"]},
    {"name": "performance-optimizer", "model_hint": "sonnet", "egress": [],
     "description": "Finds bottlenecks, reduces bundle size, and fixes memory/render/algorithmic hot paths.",
     "skills": ["profiling", "bottleneck analysis", "bundle reduction", "memory-leak hunting", "algorithmic tuning"],
     "resources": ["profiler", "flame graphs"]},
    {"name": "refactor-cleaner", "model_hint": "sonnet", "egress": [],
     "description": "Removes dead code and duplicates safely, backed by static analysis.",
     "skills": ["dead-code detection", "deduplication", "safe deletion", "consolidation"],
     "resources": ["knip", "ts-prune", "depcheck"]},
    {"name": "build-error-resolver", "model_hint": "sonnet", "egress": ["registry.npmjs.org", "pypi.org"],
     "description": "Gets the build green with minimal diffs — build/type/linker errors only, no architectural edits.",
     "skills": ["build-error triage", "type-error fixing", "dependency resolution", "minimal-diff repair"],
     "resources": ["build logs", "package registries"]},
    {"name": "silent-failure-hunter", "model_hint": "sonnet", "egress": [],
     "description": "Finds swallowed errors, bad fallbacks, and missing error propagation.",
     "skills": ["error-path audit", "fallback review", "exception-propagation check"],
     "resources": ["static analysis"]},
    {"name": "e2e-runner", "model_hint": "sonnet", "egress": [],
     "description": "Generates and runs end-to-end tests for critical flows; quarantines flaky tests.",
     "skills": ["journey design", "e2e authoring", "flake quarantine", "artifact capture"],
     "resources": ["Playwright"]},
    {"name": "docs-lookup", "model_hint": "haiku", "egress": ["context7.com", "*.context7.com"],
     "description": "Fetches current library/API documentation and returns answers with up-to-date examples.",
     "skills": ["doc retrieval", "API lookup", "example synthesis"],
     "resources": ["Context7 MCP"]},
]

_BY_ID = {m["id"]: {**m, "provider": g["provider"], "key_env": g.get("key_env")}
          for g in CATALOG for m in g["models"]}


def model_info(model_id: str) -> dict | None:
    return _BY_ID.get(model_id)


def all_model_ids() -> list[str]:
    return list(_BY_ID)
