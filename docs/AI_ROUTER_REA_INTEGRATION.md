# AI Router + REA integration plan

## Scope

This change introduces a small, provider-neutral routing layer for OpenAI-compatible chat endpoints. It is original integration code, informed by public documentation and feature comparisons. It does not copy proprietary source code, weights, prompts, or private APIs.

REA is used only for authorized inspection of software and runtime behavior. It is not a model trainer and does not automatically convert a commercial product into open source.

## Why this design

- LiteLLM documents a unified API for many model providers, retries and fallback routing. See https://docs.litellm.ai/docs/ and https://docs.litellm.ai/docs/routing.
- OpenHands documents an open, model-agnostic coding-agent platform with CLI, GUI and SDK. See https://github.com/OpenHands/OpenHands and https://www.openhands.dev/product/.
- LangGraph documents stateful, long-running agent orchestration. See https://github.com/langchain-ai/langgraph.
- Qwen3 documents Apache-2.0 model weights for its open-weight model family; verify each checkpoint's own card/license before use. See https://github.com/QwenLM/Qwen3.
- DeepSeek-V3 provides model weights under a separate model license; do not assume the code license also governs weights. See https://github.com/deepseek-ai/DeepSeek-V3.

The first implementation intentionally avoids a new gateway dependency and supports OpenAI-compatible endpoints. A later stage can add a dedicated gateway only after reviewing its current security advisories, deployment footprint, and license.

## Configuration

Set `AI_ROUTER_MODELS_JSON` to a JSON array. Each item has:

- `id`: internal short name
- `provider`: display label
- `base_url`: provider's OpenAI-compatible API base URL
- `model`: exact model identifier supported by that provider
- `api_key_env`: environment variable name containing the secret
- `tasks`: one or more of `coding`, `research`, `marketing`, `analysis`, `general`, or `*`
- `priority`: lower values are preferred
- `enabled`: optional boolean

Example (replace model IDs with the exact names provided by your vendor):

```json
[
  {
    "id": "qwen-coder",
    "provider": "Qwen-compatible endpoint",
    "base_url": "https://YOUR_OPENAI_COMPATIBLE_ENDPOINT/v1",
    "model": "YOUR_CODING_MODEL_ID",
    "api_key_env": "QWEN_API_KEY",
    "tasks": ["coding"],
    "priority": 10
  },
  {
    "id": "deepseek-general",
    "provider": "DeepSeek-compatible endpoint",
    "base_url": "https://YOUR_OPENAI_COMPATIBLE_ENDPOINT/v1",
    "model": "YOUR_GENERAL_MODEL_ID",
    "api_key_env": "DEEPSEEK_API_KEY",
    "tasks": ["research", "marketing", "analysis", "general"],
    "priority": 20
  }
]
```

Add the actual keys as Render environment variables. Never place secret values in this JSON, Git, logs, or chat. Do not use placeholder URLs in production.

## Current limitations

- Task classification is keyword-based and deliberately conservative; it is not a learned benchmark.
- Only OpenAI-compatible `/chat/completions` endpoints are supported in this first cut.
- No external browsing, shell, browser automation, code execution, or REA operation is invoked by this router.
- A model response is not proof that an external action occurred.
- Model licenses, API terms, privacy terms, pricing and regional availability must be verified before production.
- This change does not deploy itself. Merge and configure the Render service only after tests and review.
