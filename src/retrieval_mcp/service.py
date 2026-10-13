"""Bounded work, shared in-flight requests and a bounded process-local TTL cache.

A caller deadline does not cancel a running synchronous model call. Its worker
slot stays occupied until the backend finishes, preventing unbounded retries.
"""
import asyncio
from collections import Counter, OrderedDict
import json
import logging
from time import monotonic
from uuid import uuid4
from .contracts import RetrievalError, SearchRequest, SearchResult
from .settings import Settings

log = logging.getLogger('retrieval.service')

class RetrievalService:
    def __init__(self, backend, settings: Settings):
        self.backend = backend
        self.settings = settings
        self._slots = asyncio.Semaphore(settings.max_workers)
        self._tasks = {}
        self._cache = OrderedDict()
        self.counts = Counter()
        self.closed = False

    def _key(self, request):
        payload = request.model_dump(exclude={'use_cache'})
        payload['corpus_version'] = self.settings.corpus_version
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)

    async def retrieve(self, request: SearchRequest) -> SearchResult:
        started = monotonic()
        request_id = uuid4().hex
        self.counts['requests'] += 1
        key = self._key(request)
        if self.closed:
            raise RetrievalError('shutting_down', request_id=request_id)
        # All mapping operations are on the ASGI event loop, before any await.
        cached = self._cache.pop(key, None) if request.use_cache else None
        if cached and cached[0] > monotonic():
            self._cache[key] = cached
            result = cached[1].model_copy(deep=True)
            result.request_id = request_id
            result.cache = 'hit'
            result.duration_ms = round((monotonic()-started)*1000, 3)
            self.counts['cache_hits'] += 1
            return result
        shared = request.use_cache and key in self._tasks
        task_key = key if request.use_cache else uuid4().hex
        if shared:
            task = self._tasks[key]
            self.counts['shared'] += 1
        else:
            if len(self._tasks) >= self.settings.max_pending:
                self.counts['busy'] += 1
                raise RetrievalError('capacity_exceeded', 429, request_id)
            task = asyncio.create_task(self._execute(request, request_id, key))
            self._tasks[task_key] = task
            task.add_done_callback(lambda done: self._finish(task_key, done))
        try:
            result = await asyncio.wait_for(asyncio.shield(task), self.settings.request_timeout)
        except TimeoutError as error:
            self.counts['timeouts'] += 1
            raise RetrievalError('retrieval_timeout', 504, request_id) from error
        except RetrievalError as error:
            raise RetrievalError(error.code, error.status_code, request_id) from error
        result = result.model_copy(deep=True)
        result.request_id = request_id
        result.cache = 'shared' if shared else ('miss' if request.use_cache else 'bypass')
        result.duration_ms = round((monotonic()-started)*1000, 3)
        return result

    async def _execute(self, request, execution_id, key):
        async with self._slots:
            started = monotonic()
            self.counts['executions'] += 1
            try:
                result = await asyncio.to_thread(self.backend.retrieve, request, execution_id)
                result.execution_ms = round((monotonic()-started)*1000, 3)
                # Partial results and errors must be retried after recovery.
                if request.use_cache and result.status in {'ok', 'empty'} and self.settings.cache_entries:
                    self._cache[key] = (monotonic()+self.settings.cache_ttl, result.model_copy(deep=True))
                    self._cache.move_to_end(key)
                    while len(self._cache) > self.settings.cache_entries:
                        self._cache.popitem(last=False)
                self.counts['completed'] += 1
                log.info(json.dumps({'execution_id':execution_id, 'status':result.status,
                    'duration_ms':result.execution_ms, 'documents':len(result.documents)}))
                return result
            except Exception as error:
                self.counts['errors'] += 1
                # Never serialize vendor exceptions, which may contain URLs or secrets.
                log.error('execution_id=%s failure_type=%s', execution_id, type(error).__name__)
                if isinstance(error, RetrievalError):
                    raise
                raise RetrievalError('backend_failed') from error

    def _finish(self, key, task):
        self._tasks.pop(key, None)
        if not task.cancelled():
            task.exception()  # Retrieve errors even if all callers timed out/disconnected.

    def stats(self):
        return {**self.counts, 'inflight':len(self._tasks), 'cache_entries':len(self._cache)}

    async def close(self):
        self.closed = True
        if self._tasks:
            await asyncio.gather(*tuple(self._tasks.values()), return_exceptions=True)
        close = getattr(self.backend, 'close', None)
        if close:
            await asyncio.to_thread(close)
