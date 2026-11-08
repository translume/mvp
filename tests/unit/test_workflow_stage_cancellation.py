from __future__ import annotations

import asyncio

import pytest
from translume_core.workflow import _gather_workflow_stages


@pytest.mark.asyncio
async def test_parallel_stage_results_preserve_input_order():
    second_finished = asyncio.Event()

    async def first():
        await second_finished.wait()
        return "first"

    async def second():
        second_finished.set()
        return "second"

    results = await asyncio.wait_for(
        _gather_workflow_stages(first(), second()), timeout=1
    )
    assert results == ["first", "second"]


@pytest.mark.asyncio
async def test_failed_stage_cancels_and_awaits_sibling_cleanup_before_raising():
    sibling_started = asyncio.Event()
    sibling_cleaned = asyncio.Event()
    never_ready = asyncio.Event()
    failure = RuntimeError("original provider failure")

    async def failing():
        await sibling_started.wait()
        raise failure

    async def sibling():
        sibling_started.set()
        try:
            await never_ready.wait()
        finally:
            await asyncio.sleep(0)
            sibling_cleaned.set()

    with pytest.raises(RuntimeError) as raised:
        await asyncio.wait_for(_gather_workflow_stages(failing(), sibling()), timeout=1)
    assert raised.value is failure
    assert sibling_cleaned.is_set()


@pytest.mark.asyncio
async def test_cancelling_workflow_drains_every_parallel_stage():
    started = [asyncio.Event(), asyncio.Event()]
    cleaned = [asyncio.Event(), asyncio.Event()]
    never_ready = asyncio.Event()

    async def stage(index):
        started[index].set()
        try:
            await never_ready.wait()
        finally:
            await asyncio.sleep(0)
            cleaned[index].set()

    task = asyncio.create_task(_gather_workflow_stages(stage(0), stage(1)))
    await asyncio.wait_for(
        asyncio.gather(*(event.wait() for event in started)), timeout=1
    )
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert all(event.is_set() for event in cleaned)
