import asyncio
import json
import stat

import pytest

from workshop.agent_benchmark.broker import ModelBroker


async def exchange(path, request):
    reader, writer = await asyncio.open_unix_connection(str(path))
    writer.write(json.dumps(request).encode() + b"\n")
    await writer.drain()
    result = json.loads(await reader.readline())
    writer.close()
    await writer.wait_closed()
    return result


def request(token, **extra):
    return {
        "version": 1,
        "token": token,
        "messages": [{"role": "user", "content": "hello"}],
    } | extra


def test_broker_round_trip_and_socket_cleanup(tmp_path):
    async def run():
        seen = []

        async def provider(messages):
            seen.append(messages)
            return "answer"

        broker = ModelBroker(tmp_path, provider)
        async with broker:
            assert stat.S_IMODE(broker.socket_path.stat().st_mode) == 0o600
            response = await exchange(
                broker.socket_path, request(broker.token)
            )
            assert response == {"ok": True, "content": "answer"}
            assert seen == [[{"role": "user", "content": "hello"}]]
        assert not broker.socket_path.exists()

    asyncio.run(run())


def test_broker_instance_cannot_be_reused(tmp_path):
    async def run():
        async def provider(messages):
            return "ok"

        broker = ModelBroker(tmp_path, provider)
        async with broker:
            pass
        with pytest.raises(RuntimeError, match="single-use"):
            async with broker:
                pass

    asyncio.run(run())


def test_broker_rejects_invalid_auth_and_routing_override(tmp_path):
    async def run():
        calls = []

        async def provider(messages):
            calls.append(messages)
            return "ok"

        async with ModelBroker(tmp_path, provider) as broker:
            assert not (await exchange(broker.socket_path, request("wrong")))[
                "ok"
            ]
            assert not (
                await exchange(
                    broker.socket_path, request(broker.token, model="other")
                )
            )["ok"]
            assert not (
                await exchange(
                    broker.socket_path,
                    request(broker.token, url="http://example"),
                )
            )["ok"]
        assert not calls

    asyncio.run(run())


def test_broker_rejects_cross_run_credentials(tmp_path):
    async def run():
        async def provider(messages):
            return "ok"

        first_dir, second_dir = tmp_path / "one", tmp_path / "two"
        first_dir.mkdir(mode=0o700)
        second_dir.mkdir(mode=0o700)
        async with ModelBroker(first_dir, provider) as first:
            async with ModelBroker(second_dir, provider) as second:
                assert first.token != second.token
                assert not (
                    await exchange(second.socket_path, request(first.token))
                )["ok"]

    asyncio.run(run())


def test_broker_rejects_oversized_and_malformed_frames(tmp_path):
    async def run():
        async def provider(messages):
            pytest.fail("provider should not be called")

        async with ModelBroker(tmp_path, provider) as broker:
            reader, writer = await asyncio.open_unix_connection(
                str(broker.socket_path)
            )
            writer.write(b"x" * (256 * 1024 + 10) + b"\n")
            await writer.drain()
            assert not json.loads(await reader.readline())["ok"]
            writer.close()
            await writer.wait_closed()
            assert not (
                await exchange(broker.socket_path, {"token": broker.token})
            )["ok"]

    asyncio.run(run())


def test_broker_request_limit_and_provider_error_do_not_leak(tmp_path):
    async def run():
        calls = 0

        async def provider(messages):
            nonlocal calls
            calls += 1
            raise RuntimeError("private provider secret")

        async with ModelBroker(tmp_path, provider, max_requests=2) as broker:
            for _ in range(3):
                response = await exchange(
                    broker.socket_path, request(broker.token)
                )
                assert not response["ok"]
                assert "secret" not in repr(response)
            assert calls == 2

    asyncio.run(run())


def test_broker_rejects_concurrency_and_times_out_provider(tmp_path):
    async def run():
        started = asyncio.Event()

        async def provider(messages):
            started.set()
            await asyncio.sleep(10)
            return "late"

        async with ModelBroker(
            tmp_path, provider, timeout_seconds=0.1
        ) as broker:
            task = asyncio.create_task(
                exchange(broker.socket_path, request(broker.token))
            )
            await started.wait()
            response = await exchange(
                broker.socket_path, request(broker.token)
            )
            assert response["error"] == "busy"
            response = await task
            assert response["error"] == "timeout"

    asyncio.run(run())


def test_broker_shutdown_cancels_inflight_provider(tmp_path):
    async def run():
        started = asyncio.Event()
        cancelled = asyncio.Event()

        async def provider(messages):
            started.set()
            try:
                await asyncio.sleep(30)
            finally:
                cancelled.set()

        async with ModelBroker(tmp_path, provider) as broker:
            reader, writer = await asyncio.open_unix_connection(
                str(broker.socket_path)
            )
            writer.write(json.dumps(request(broker.token)).encode() + b"\n")
            await writer.drain()
            await started.wait()
        assert cancelled.is_set()
        assert not broker.socket_path.exists()
        writer.close()
        await writer.wait_closed()
        assert await reader.read() == b""

    asyncio.run(run())


def test_broker_rejects_oversized_provider_response(tmp_path):
    async def run():
        async def provider(messages):
            return "x" * (1024 * 1024 + 1)

        async with ModelBroker(tmp_path, provider) as broker:
            response = await exchange(
                broker.socket_path, request(broker.token)
            )
            assert response == {"ok": False, "error": "provider failure"}

    asyncio.run(run())


def test_broker_rejects_duplicate_json_fields(tmp_path):
    async def run():
        async def provider(messages):
            pytest.fail("provider should not be called")

        async with ModelBroker(tmp_path, provider) as broker:
            reader, writer = await asyncio.open_unix_connection(
                str(broker.socket_path)
            )
            payload = json.dumps(request(broker.token))
            writer.write((payload[:-1] + ', "version": 1}\n').encode())
            await writer.drain()
            assert not json.loads(await reader.readline())["ok"]
            writer.close()
            await writer.wait_closed()

    asyncio.run(run())


def test_broker_rejects_insecure_directory_and_existing_socket_path(tmp_path):
    async def run():
        async def provider(messages):
            return "ok"

        unsafe = tmp_path / "unsafe"
        unsafe.mkdir(mode=0o755)
        unsafe.chmod(0o755)
        with pytest.raises(PermissionError):
            async with ModelBroker(unsafe, provider):
                pass
        existing = tmp_path / "broker.sock"
        existing.write_text("do not delete")
        with pytest.raises(FileExistsError):
            async with ModelBroker(tmp_path, provider):
                pass
        assert existing.read_text() == "do not delete"

    asyncio.run(run())
