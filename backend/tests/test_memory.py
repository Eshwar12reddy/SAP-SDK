def test_memory_module_exists():
    from app.services import memory_service
    assert memory_service.context
