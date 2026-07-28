def test_package_imports():
    """The suite exists so `tessera-test` is green-meaningful, not green-empty."""
    import arbiter

    assert callable(arbiter.main)
