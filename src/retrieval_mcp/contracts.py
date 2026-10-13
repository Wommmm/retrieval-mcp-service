"""The same explicit contract is used by HTTP, MCP, evaluation and the client."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Route = Literal['vector', 'hyde', 'kg', 'web']

class SearchRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    query: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=20)
    routes: list[Route] = Field(default_factory=lambda: ['vector', 'hyde', 'kg'])
    rerank: bool = True
    use_cache: bool = True

    @field_validator('query')
    @classmethod
    def nonblank(cls, value):
        value = value.strip()
        if not value:
            raise ValueError('query must not be blank')
        return value

    @field_validator('routes')
    @classmethod
    def canonical_routes(cls, value):
        if 'vector' not in value:
            raise ValueError('vector is the required retrieval route')
        return sorted(set(value))

class Document(BaseModel):
    id: str
    content: str
    source: Literal['local', 'web', 'demo']
    title: str = ''
    chunk_id: str | None = None
    url: str = ''
    score: float | None = Field(default=None, allow_inf_nan=False)
    score_type: Literal['rerank', 'rrf', 'lexical', 'unscored'] = 'unscored'

class StageTrace(BaseModel):
    stage: str
    status: Literal['ok', 'empty', 'error', 'skipped']
    duration_ms: float = Field(ge=0)
    documents: int = Field(default=0, ge=0)
    error_code: str | None = None

class SearchResult(BaseModel):
    schema_version: str = '1.0'
    request_id: str
    execution_id: str
    backend: Literal['demo', 'live']
    status: Literal['ok', 'empty', 'partial', 'clarification']
    documents: list[Document] = Field(default_factory=list)
    message: str = ''
    warnings: list[str] = Field(default_factory=list)
    traces: list[StageTrace] = Field(default_factory=list)
    cache: Literal['miss', 'hit', 'shared', 'bypass'] = 'miss'
    duration_ms: float = 0
    execution_ms: float = 0

class RetrievalError(Exception):
    def __init__(self, code: str, status_code: int = 503, request_id: str = ''):
        super().__init__(code)
        self.code = code
        self.status_code = status_code
        self.request_id = request_id
