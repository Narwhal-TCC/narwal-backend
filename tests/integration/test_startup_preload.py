from app.services.model_registry import DEFAULT_MODEL_ID


def test_bootstrap_preloads_only_default_pipeline(monkeypatch, production_bootstrap):
    preload_calls: list[str] = []

    class _Gateway:
        def ensure_model_loaded(self):
            return self

    class _SpyPool:
        def get(self, model_id: str):
            preload_calls.append(model_id)
            return _Gateway()

    monkeypatch.setattr("app.main.get_gateway_pool", lambda: _SpyPool())
    monkeypatch.setattr("app.main.S3ObjectStore.ensure_bucket", lambda self: None)
    monkeypatch.setattr("app.main.seed_v2_model_artifacts", lambda _store: None)
    monkeypatch.setattr(
        "app.main.S3ObjectStore.seed_model_if_missing",
        lambda self, *args, **kwargs: False,
    )
    monkeypatch.setattr("app.main.run_seed", lambda: None)

    production_bootstrap()

    assert preload_calls == [DEFAULT_MODEL_ID]
