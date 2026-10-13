"""Retrieval-only LangGraph, with inherited nodes behind a stable service boundary."""
from hashlib import sha256
from threading import Lock
from time import monotonic
from typing import Any, TypedDict
import os
from .contracts import Document, RetrievalError, SearchResult, StageTrace

class LiveState(TypedDict, total=False):
    original_query: str
    rewritten_query: str
    item_names: list[str]
    retrieval_only: bool
    answer: str
    embedding_chunks: list
    hyde_embedding_chunks: list
    kg_chunks: list
    kg_triples: list
    web_search_docs: list
    rrf_chunks: list
    reranked_docs: list

class LiveBackend:
    def __init__(self):
        # Importing this adapter is cheap; optional model packages load on first work.
        self._model_lock = Lock()

    def retrieve(self, request, execution_id):
        # Local CPU BGE singleton use is serialized intentionally. No cancelled
        # request releases this lock while its model inference is still running.
        with self._model_lock:
            return self._run(request, execution_id)

    def _run(self, request, execution_id):
        from langgraph.graph import StateGraph, START, END
        from .vendor.processor.query_process.nodes.item_name_confirm_node import ItemNameConfirmNode
        from .vendor.processor.query_process.nodes.vector_search_node import VectorSearchNode
        from .vendor.processor.query_process.nodes.hyde_search_node import HyDeSearchNode
        from .vendor.processor.query_process.nodes.kg_search_node import KnowledgeGraphSearchNode
        from .vendor.processor.query_process.nodes.rrf_node import RrfNode
        from .vendor.processor.query_process.nodes.rerank_node import RerankNode
        traces, warnings = [], []

        def stage(name, function, fields, optional=False):
            def run(state):
                started = monotonic()
                try:
                    result = function(dict(state))
                    update = {key: result[key] for key in fields if key in result}
                    count = sum(len(v) for key,v in update.items() if key.endswith(('_chunks', '_docs')) and isinstance(v,list))
                    traces.append(StageTrace(stage=name, status='ok' if count or name=='identify' else 'empty',
                        duration_ms=round((monotonic()-started)*1000,3), documents=count))
                    return update
                except Exception as error:
                    traces.append(StageTrace(stage=name, status='error', duration_ms=round((monotonic()-started)*1000,3),
                        error_code=name+'_failed'))
                    if not optional:
                        raise RetrievalError(name+'_failed') from error
                    warnings.append(name+'_failed')
                    return {field:[] for field in fields}
            return run

        def kg(state):
            from .vendor.utils.neo4j_util import get_neo4j_driver
            driver = get_neo4j_driver()
            if driver is None:
                raise RuntimeError('Graph dependency unavailable')
            driver.verify_connectivity()
            return KnowledgeGraphSearchNode().process(state)

        def web(state):
            if not os.getenv('MCP_DASHSCOPE_BASE_URL'):
                raise RuntimeError('External search is not configured')
            from .vendor.processor.query_process.nodes.mcp_search_node import McpSearchNode
            return McpSearchNode().process(state)

        workflow = StateGraph(LiveState)
        workflow.add_node('identify', stage('identify', ItemNameConfirmNode().process, ['rewritten_query','item_names','answer']))
        workflow.add_edge(START, 'identify')
        workflow.add_node('vector', stage('vector', VectorSearchNode().process, ['embedding_chunks']))
        workflow.add_conditional_edges('identify', lambda state: 'stop' if state.get('answer') else 'search',
            {'stop':END, 'search':'vector'})
        previous = 'vector'
        for name, function, fields in [
            ('hyde', HyDeSearchNode().process, ['hyde_embedding_chunks']),
            ('kg', kg, ['kg_chunks','kg_triples']),
            ('web', web, ['web_search_docs']),
        ]:
            if name not in request.routes:
                traces.append(StageTrace(stage=name,status='skipped',duration_ms=0))
                continue
            workflow.add_node(name, stage(name,function,fields,optional=True))
            workflow.add_edge(previous, name)
            previous = name
        workflow.add_node('fuse', stage('fuse', RrfNode().process, ['rrf_chunks']))
        workflow.add_edge(previous, 'fuse')
        if request.rerank:
            workflow.add_node('rerank', stage('rerank', RerankNode().process,['reranked_docs']))
            workflow.add_edge('fuse','rerank')
            workflow.add_edge('rerank',END)
        else:
            workflow.add_edge('fuse', END)
        state = workflow.compile().invoke({'original_query':request.query, 'retrieval_only':True})
        if state.get('answer'):
            return SearchResult(request_id=execution_id,execution_id=execution_id,backend='live',
                status='clarification',message=state['answer'],traces=traces)
        rows = state.get('reranked_docs',[]) if request.rerank else state.get('rrf_chunks',[])
        if not request.rerank:
            rows = [dict(row,source='local') for row in rows]
            rows += [dict(row,source='web') for row in state.get('web_search_docs',[])]
        documents, seen = [], set()
        for row in rows:
            content = str(row.get('content') or row.get('snippet') or '').strip()
            if not content:
                continue
            chunk_id = str(row['chunk_id']) if row.get('chunk_id') is not None else None
            source = row.get('source','local')
            url = row.get('url') or ''
            identity = sha256((source+'|'+str(chunk_id or url)+'|'+content).encode()).hexdigest()[:24]
            if identity in seen:
                continue
            seen.add(identity)
            documents.append(Document(id=identity,content=content,source=source,chunk_id=chunk_id,
                url=url,title=row.get('title') or row.get('item_name') or 'Knowledge base document',score=row.get('score'),
                score_type='rerank' if request.rerank else ('rrf' if source=='local' else 'unscored')))
        documents = documents[:request.top_k]
        return SearchResult(request_id=execution_id,execution_id=execution_id,backend='live',
            status='partial' if warnings else ('ok' if documents else 'empty'),
            documents=documents,warnings=warnings,traces=traces)

    def close(self):
        # Optional dependencies are only imported if live requests actually ran.
        import sys
        for module_name, attribute in [('milvus_util','milvus_client'),('neo4j_util','_neo4j_driver')]:
            module = sys.modules.get('retrieval_mcp.vendor.utils.'+module_name)
            instance = getattr(module,attribute,None) if module else None
            if instance is not None:
                instance.close()
                setattr(module,attribute,None)
