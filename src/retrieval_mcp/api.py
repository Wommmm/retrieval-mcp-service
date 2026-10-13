from contextlib import asynccontextmanager
import hmac
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from mcp.server.fastmcp import FastMCP
from .contracts import RetrievalError, SearchRequest, SearchResult
from .settings import Settings
from .service import RetrievalService

def create_app(settings=None, backend=None):
    settings = settings or Settings.from_env()
    if backend is None:
        if settings.backend == 'live':
            from .live import LiveBackend
            backend = LiveBackend()
        else:
            from .demo import DemoBackend
            backend = DemoBackend()
    service = RetrievalService(backend, settings)
    mcp = FastMCP('Independent Retrieval Service', stateless_http=True,
        json_response=True, streamable_http_path='/')

    @mcp.tool()
    async def search_knowledge(query: str, top_k: int = 5) -> SearchResult:
        """Retrieve attributed evidence, not a final answer. Inspect status and warnings.

        empty means no evidence; partial means an optional route failed;
        clarification requests a more specific product name. Do not invent evidence.
        """
        try:
            return await service.retrieve(SearchRequest(query=query,top_k=top_k))
        except RetrievalError as error:
            raise RuntimeError(f'{error.code}; request_id={error.request_id}') from None

    mcp_app = mcp.streamable_http_app()

    @asynccontextmanager
    async def lifespan(app):
        async with mcp.session_manager.run():
            yield
            await service.close()

    app = FastAPI(title='Independent Retrieval Service', version='0.1.0', lifespan=lifespan)
    app.state.service = service

    @app.middleware('http')
    async def authentication(request: Request, call_next):
        if settings.api_token and request.url.path != '/health/live':
            expected = 'Bearer '+settings.api_token
            supplied = request.headers.get('authorization','')
            if not hmac.compare_digest(supplied.encode(),expected.encode()):
                return JSONResponse({'error':'unauthorized'},status_code=401)
        return await call_next(request)

    @app.exception_handler(RetrievalError)
    async def failure(request, error):
        return JSONResponse({'error':{'code':error.code,'request_id':error.request_id}},
            status_code=error.status_code,headers={'Retry-After':'5'} if error.status_code==429 else None)

    @app.get('/health/live')
    async def live():
        # Liveness only; do not claim model/database readiness from this endpoint.
        return {'status':'alive','backend':settings.backend}

    @app.get('/stats')
    async def stats():
        return service.stats()

    @app.post('/v1/retrieve', response_model=SearchResult)
    async def retrieve(request: SearchRequest):
        return await service.retrieve(request)

    app.mount('/mcp',mcp_app)
    return app
