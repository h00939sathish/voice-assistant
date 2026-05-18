from assistant.app_init import ComponentHandle


def test_component_handle_can_receive_background_components():
    handle = ComponentHandle()
    wake = object()
    task_executor = object()

    handle.set_wake_detector(wake)
    handle.set_task_executor(task_executor)

    assert handle.wake_detector is wake
    assert handle.task_executor is task_executor
