import asyncio

import pytest
from unittest.mock import AsyncMock, MagicMock

from okta_jwt_verifier import BaseJWTVerifier, __version__ as version
from okta_jwt_verifier.request_executor import RequestExecutor


@pytest.mark.asyncio
async def test_proxy():
    """Test that proxy parameter is passed to requests."""
    issuer = 'https://test.okta.com'

    # Without proxy
    verifier = BaseJWTVerifier(issuer)
    verifier.request_executor.fire_request = AsyncMock(return_value={'keys': []})
    await verifier.get_jwks()

    verifier.request_executor.fire_request.assert_called_with(
        f'{issuer}/oauth2/v1/keys',
        headers={'User-Agent': f'okta-jwt-verifier-python/{version}',
                 'Content-Type': 'application/json'},
        timeout=30
    )

    # With proxy
    verifier = BaseJWTVerifier(issuer, proxy='http://proxy:8080')
    verifier.request_executor.fire_request = AsyncMock(return_value={'keys': []})
    await verifier.get_jwks()

    verifier.request_executor.fire_request.assert_called_with(
        f'{issuer}/oauth2/v1/keys',
        headers={'User-Agent': f'okta-jwt-verifier-python/{version}',
                 'Content-Type': 'application/json'},
        timeout=30,
        proxy='http://proxy:8080'
    )


@pytest.mark.asyncio
async def test_retry_success():
    """Test that transient failures are retried."""
    executor = RequestExecutor(max_retries=3)
    executor.fire_request = AsyncMock(side_effect=[
        Exception('fail'),
        Exception('fail'),
        {'keys': []}
    ])

    result = await executor.get('https://test.com/keys')

    assert result == {'keys': []}
    assert executor.fire_request.call_count == 3


@pytest.mark.asyncio
async def test_retry_exhausted():
    """Test that exception is raised when retries exhausted."""
    executor = RequestExecutor(max_retries=2)
    executor.fire_request = AsyncMock(side_effect=Exception('network error'))

    with pytest.raises(Exception):
        await executor.get('https://test.com/keys')

    assert executor.fire_request.call_count == 2


@pytest.mark.asyncio
async def test_clear_cache():
    """Test that clear_cache calls underlying cache."""
    executor = RequestExecutor()
    executor.cache.clear_cache = MagicMock()

    executor.clear_cache()

    executor.cache.clear_cache.assert_called_once()


def test_retry_success_sync():
    """Test that transient failures are retried on the sync path."""
    executor = RequestExecutor(max_retries=3)
    executor._backoff_delay = MagicMock(return_value=0)
    executor.fire_request_sync = MagicMock(side_effect=[
        Exception('fail'),
        Exception('fail'),
        {'keys': []}
    ])

    result = executor.get_sync('https://test.com/keys')

    assert result == {'keys': []}
    assert executor.fire_request_sync.call_count == 3
    assert executor.requests_count == 0


def test_retry_exhausted_sync():
    """Test that the last exception is raised when sync retries are exhausted."""
    executor = RequestExecutor(max_retries=2)
    executor._backoff_delay = MagicMock(return_value=0)
    executor.fire_request_sync = MagicMock(side_effect=Exception('network error'))

    with pytest.raises(Exception, match='network error'):
        executor.get_sync('https://test.com/keys')

    assert executor.fire_request_sync.call_count == 2
    assert executor.requests_count == 0


@pytest.mark.asyncio
async def test_async_get_does_not_block_event_loop():
    """Test that async retry backoff yields to other tasks on the event loop."""
    executor = RequestExecutor(max_retries=2)
    executor.fire_request = AsyncMock(side_effect=[Exception('fail'), {'keys': []}])
    order = []

    async def fetch():
        result = await executor.get('https://test.com/keys')
        order.append('get')
        return result

    async def ticker():
        for _ in range(3):
            await asyncio.sleep(0.01)
        order.append('ticker')

    result, _ = await asyncio.gather(fetch(), ticker())

    assert result == {'keys': []}
    # The 0.5s retry backoff must let the ticker finish first.
    assert order == ['ticker', 'get']
