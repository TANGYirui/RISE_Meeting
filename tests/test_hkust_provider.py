from rise.decompose import provider_config, resolve_model


def test_hkust_provider_uses_meetingrag_environment_contract(monkeypatch):
    monkeypatch.setenv("HKUST_GENAI_API_KEY", "secret")
    monkeypatch.setenv(
        "HKUST_GENAI_ENDPOINT",
        "https://hkust.azure-api.net/hkust-genai/v1/chat/completions",
    )
    monkeypatch.setenv("HKUST_GENAI_MODEL", "gemini-3-flash-preview")

    config = provider_config("gemini-3-flash-preview")

    assert config.api_key == "secret"
    assert config.base_url == "https://hkust.azure-api.net/hkust-genai/v1"
    assert config.default_headers == {"api-key": "secret"}


def test_hkust_configuration_overrides_upstream_default_models(monkeypatch):
    monkeypatch.setenv("HKUST_GENAI_API_KEY", "secret")
    monkeypatch.setenv("HKUST_GENAI_MODEL", "gemini-3-flash-preview")

    assert resolve_model("deepseek-chat") == "gemini-3-flash-preview"
    assert provider_config("deepseek-chat").base_url == "https://hkust.azure-api.net/hkust-genai/v1"
