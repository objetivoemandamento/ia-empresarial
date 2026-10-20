from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class ModelRoute:
    task: str
    model: str
    reason: str


# OpenRouter model IDs verified against its public model pages (October 2026).
# These are open-weight models; licenses and commercial restrictions still vary.
OPENROUTER_DEFAULTS = {
    "general": "deepseek/deepseek-v4.1-flash-1017",
    "reasoning": "moonshotai/kimi-k3",
    "coding": "z-ai/glm-5.3",
    "research": "qwen/qwen3.8-max-0902",
    "reverse_engineering": "deepseek/deepseek-v4.1-flash-1017",
    "marketing": "qwen/qwen3.8-max-0902",
}

_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("reverse_engineering", (
        r"engenharia reversa", r"reverse.engineer", r"binário", r"binary",
        r"apk", r"firmware", r"decompil", r"rea-agents", r"rea\b",
        r"analisar.*aplicativo", r"inspecionar.*aplicativo",
    )),
    ("coding", (
        r"\b(código|codigo|programar|programação|programacao|debug|bug|stack trace|"
        r"api|backend|frontend|deploy|deployar|typescript|python|javascript|sql|"
        r"repositório|repositorio|github|render|docker|teste unitário|testes?)\b",
    )),
    ("research", (
        r"pesquisa profunda", r"pesquise", r"pesquisa", r"fontes", r"atualizado",
        r"comparar modelos", r"benchmark", r"mercado", r"concorrentes",
    )),
    ("marketing", (
        r"marketing", r"divulgação", r"divulgacao", r"campanha", r"copywriting",
        r"anúncio", r"anuncio", r"vendas", r"produto digital", r"página de vendas",
        r"pagina de vendas", r"instagram", r"whatsapp",
    )),
    ("reasoning", (
        r"raciocínio", r"raciocinio", r"estratégia", r"estrategia", r"arquitetura",
        r"plano complexo", r"decisão", r"decisao", r"análise profunda", r"analise profunda",
        r"multi.agente", r"orquestra",
    )),
)


def classify_task(messages: Iterable[dict[str, str]]) -> tuple[str, str]:
    """Conservative keyword routing. It does not execute tools or infer permissions."""
    latest = next(
        (str(item.get("content", "")) for item in reversed(list(messages))
         if item.get("role") == "user"),
        "",
    )
    text = latest.lower()
    for task, patterns in _PATTERNS:
        if any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns):
            return task, f"Matched task signals for {task}"
    return "general", "No specialist task signal; using general model"


def select_model(
    messages: list[dict[str, str]],
    base_url: str,
    fallback_model: str,
    overrides: dict[str, str] | None = None,
) -> ModelRoute:
    task, reason = classify_task(messages)
    overrides = overrides or {}
    is_openrouter = "openrouter.ai" in base_url.lower()
    defaults = OPENROUTER_DEFAULTS if is_openrouter else {}
    model = (overrides.get(task) or defaults.get(task) or fallback_model).strip()
    return ModelRoute(task=task, model=model, reason=reason)
