def test_imports():
    import api  # noqa: F401
    from handlers import __init__ as _h  # noqa: F401  # package exists
    from routers import __init__ as _r  # noqa: F401  # package exists
    from handlers.ai import AiHandler

    assert AiHandler is not None
