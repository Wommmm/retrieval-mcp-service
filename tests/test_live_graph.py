"""Graph behavior with replaced dependencies. These are NOT live quality tests."""
import pytest
from retrieval_mcp.contracts import SearchRequest, RetrievalError
from retrieval_mcp.live import LiveBackend

@pytest.fixture
def nodes(monkeypatch):
    from retrieval_mcp.vendor.processor.query_process.nodes.item_name_confirm_node import ItemNameConfirmNode
    from retrieval_mcp.vendor.processor.query_process.nodes.vector_search_node import VectorSearchNode
    from retrieval_mcp.vendor.processor.query_process.nodes.hyde_search_node import HyDeSearchNode
    from retrieval_mcp.vendor.processor.query_process.nodes.rerank_node import RerankNode
    monkeypatch.setattr(ItemNameConfirmNode,'process',lambda self,state:{'rewritten_query':state['original_query'],'item_names':['RS-12']})
    monkeypatch.setattr(VectorSearchNode,'process',lambda self,state:{'embedding_chunks':[{'entity':{'chunk_id':1,'content':'battery document'}}]})
    monkeypatch.setattr(RerankNode,'process',lambda self,state:{'reranked_docs':[dict(doc,source='local') for doc in state['rrf_chunks']]})
    return ItemNameConfirmNode,VectorSearchNode,HyDeSearchNode

def test_optional_failure_is_partial(nodes,monkeypatch):
    def broken(self,state): raise ConnectionError('private')
    monkeypatch.setattr(nodes[2],'process',broken)
    result=LiveBackend().retrieve(SearchRequest(query='battery',routes=['vector','hyde']), 'test')
    assert result.status=='partial'
    assert result.warnings==['hyde_failed']
    assert len(result.documents)==1
    assert result.documents[0].chunk_id=='1'
    assert 'private' not in result.model_dump_json()

def test_required_failure_is_error(nodes,monkeypatch):
    def broken(self,state): raise ConnectionError('private')
    monkeypatch.setattr(nodes[1],'process',broken)
    with pytest.raises(RetrievalError,match='vector_failed'):
        LiveBackend().retrieve(SearchRequest(query='battery',routes=['vector']), 'test')

def test_clarification_stops_before_search(nodes,monkeypatch):
    monkeypatch.setattr(nodes[0],'process',lambda self,state:{'answer':'Which product?'})
    def forbidden(self,state): raise AssertionError('must not search')
    monkeypatch.setattr(nodes[1],'process',forbidden)
    result=LiveBackend().retrieve(SearchRequest(query='unclear'),'test')
    assert result.status=='clarification'
    assert result.message=='Which product?'
    assert result.documents==[]

def test_rrf_scores_are_not_raw_distance(nodes):
    result=LiveBackend().retrieve(SearchRequest(query='battery',routes=['vector'],rerank=False),'test')
    assert result.documents[0].score==pytest.approx(1/61)
    assert result.documents[0].score_type=='rrf'

def test_filter_escapes_names():
    from retrieval_mcp.vendor.processor.query_process.nodes.vector_search_node import VectorSearchNode
    name='a" or true or item_name == "b'
    value=VectorSearchNode()._item_name_filter([name])
    assert '\\"' in value
