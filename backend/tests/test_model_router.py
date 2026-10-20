from app.model_router import classify_task, select_model


def test_routes_reverse_engineering_before_generic_coding():
    task, _ = classify_task([{"role": "user", "content": "Use REA for engenharia reversa de um APK"}])
    assert task == "reverse_engineering"


def test_routes_marketing_request():
    task, _ = classify_task([{"role": "user", "content": "Crie uma campanha de divulgação para vender meu produto digital"}])
    assert task == "marketing"


def test_routes_to_openrouter_model():
    route = select_model(
        [{"role": "user", "content": "Pesquise fontes e compare modelos"}],
        "https://openrouter.ai/api/v1",
        "fallback-model",
    )
    assert route.task == "research"
    assert route.model == "qwen/qwen3.8-max-0902"


def test_non_openrouter_preserves_configured_model():
    route = select_model(
        [{"role": "user", "content": "Crie uma campanha de divulgação"}],
        "https://api.example.com/v1",
        "provider-model",
    )
    assert route.model == "provider-model"


def test_custom_override_wins():
    route = select_model(
        [{"role": "user", "content": "Escreva código Python"}],
        "https://openrouter.ai/api/v1",
        "fallback-model",
        {"coding": "custom/coder"},
    )
    assert route.model == "custom/coder"
