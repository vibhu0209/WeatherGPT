from app.models import Settings
from app.providers import PROVIDERS, WeatherProvider


def test_all_primary_adapters_implement_typed_contract():
    assert len(PROVIDERS) == 4
    for adapter in PROVIDERS:
        provider = adapter(None, Settings())
        assert isinstance(provider, WeatherProvider)
        assert provider.id and provider.display_name and provider.model_family
        assert set(provider.capabilities()) == {"current", "hourly", "daily", "alerts", "historical"}
        status = provider.health()
        assert status["provider"] == provider.id
        assert status["status"] in {"configured", "not_configured"}
