import asyncio
import threading
import time
import pytest
from fastapi.testclient import TestClient
from retrieval_mcp.api import create_app
from retrieval_mcp.contracts import SearchRequest, RetrievalError
from retrieval_mcp.demo import DemoBackend
from retrieval_mcp.service import RetrievalService
from retrieval_mcp.settings import Settings

@pytest.mark.parametrize('payload', [{}, {'query':''},{'query':'  '},{'query':'x','routes':['kg']},{'query':'x','top_k':0}])
def test_http_invalid_input(payload):
    with TestClient(create_app()) as client:
        assert client.post('/v1/retrieve',json=payload).status_code==422

def test_http_success_empty_and_shared_contract():
    with TestClient(create_app()) as client:
        result=client.post('/v1/retrieve',json={'query':'电池'}).json()
        assert result['documents'][0]['source']=='demo'
        assert result['status']=='ok'
        assert client.post('/v1/retrieve',json={'query':'no matches'}).json()['status']=='empty'
        cached=client.post('/v1/retrieve',json={'query':'电池'}).json()
        assert cached['cache']=='hit'
        assert cached['execution_id']==result['execution_id']
        assert cached['request_id']!=result['request_id']

def test_exception_redaction_and_authentication():
    class Broken:
        def retrieve(self,*args): raise ValueError('private credential')
    with TestClient(create_app(Settings(api_token='test-token'),Broken())) as client:
        assert client.get('/health/live').status_code==200
        assert client.post('/v1/retrieve',json={'query':'x'}).status_code==401
        response=client.post('/v1/retrieve',json={'query':'x'},headers={'Authorization':'Bearer test-token'})
        assert response.status_code==503
        assert response.json()['error']['code']=='backend_failed'
        assert 'credential' not in response.text

def test_singleflight_cache_copy_bypass_ttl_and_capacity():
    class Counting(DemoBackend):
        calls=0
        def retrieve(self,*args):
            self.calls+=1
            time.sleep(.02)
            return super().retrieve(*args)
    async def run():
        backend=Counting()
        service=RetrievalService(backend,Settings(cache_ttl=.04,cache_entries=1))
        req=SearchRequest(query='电池')
        results=await asyncio.gather(*(service.retrieve(req) for _ in range(5)))
        assert backend.calls==1
        assert len({r.request_id for r in results})==5
        assert sum(r.cache=='shared' for r in results)==4
        results[0].documents.clear()
        assert (await service.retrieve(req)).documents
        await service.retrieve(SearchRequest(query='温度'))
        assert service.stats()['cache_entries']==1
        await service.retrieve(req)
        assert backend.calls==3
        await service.retrieve(req.model_copy(update={'use_cache':False}))
        assert backend.calls==4
        await asyncio.sleep(.06)
        await service.retrieve(req)
        assert backend.calls==5
        await service.close()
    asyncio.run(run())

def test_timeout_keeps_worker_reserved_and_rejects_unbounded_work():
    gate=threading.Event()
    class Slow(DemoBackend):
        def retrieve(self,*args):
            gate.wait(2)
            return super().retrieve(*args)
    async def run():
        service=RetrievalService(Slow(),Settings(request_timeout=.02,max_pending=1))
        try:
            with pytest.raises(RetrievalError,match='retrieval_timeout'):
                await service.retrieve(SearchRequest(query='电池'))
            assert service.stats()['inflight']==1
            with pytest.raises(RetrievalError,match='capacity_exceeded'):
                await service.retrieve(SearchRequest(query='温度'))
            assert service.stats()['executions']==1
        finally:
            gate.set()
            await service.close()
    asyncio.run(run())

def test_partial_results_and_failures_are_not_cached():
    class Partial(DemoBackend):
        def retrieve(self,*args):
            result=super().retrieve(*args)
            result.status='partial'
            result.warnings=['kg_failed']
            return result
    async def run():
        service=RetrievalService(Partial(),Settings())
        for _ in range(2):
            await service.retrieve(SearchRequest(query='电池'))
        assert service.stats()['executions']==2
        assert service.stats()['cache_entries']==0
        await service.close()
    asyncio.run(run())

def test_cache_key_includes_pipeline_options():
    async def run():
        service=RetrievalService(DemoBackend(),Settings())
        for changes in [{},{'rerank':False},{'top_k':1},{'routes':['vector']}]:
            await service.retrieve(SearchRequest(query='电池',**changes))
        assert service.stats()['executions']==4
        await service.close()
    asyncio.run(run())
