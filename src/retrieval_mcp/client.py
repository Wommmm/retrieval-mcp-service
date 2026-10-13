"""Small SDK client; can be wrapped by a LangChain tool in the Agent consumer."""
import asyncio
import json
import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from .contracts import SearchResult

async def search(query: str, url='http://127.0.0.1:8050/mcp/', token='') -> SearchResult:
    headers = {'Authorization':'Bearer '+token} if token else None
    async with httpx.AsyncClient(headers=headers, timeout=200, trust_env=False) as client:
        async with streamable_http_client(url,http_client=client) as (read,write,_):
            async with ClientSession(read,write) as session:
                await session.initialize()
                reply = await session.call_tool('search_knowledge',{'query':query})
                if reply.isError:
                    raise RuntimeError('MCP retrieval failed; inspect server diagnostics')
                payload = reply.structuredContent
                if payload is None:
                    texts = [block.text for block in reply.content if block.type=='text']
                    if len(texts)!=1:
                        raise ValueError('Invalid retrieval response')
                    payload = json.loads(texts[0])
                return SearchResult.model_validate(payload)

def main():
    import argparse, os
    parser=argparse.ArgumentParser()
    parser.add_argument('query')
    parser.add_argument('--url',default='http://127.0.0.1:8050/mcp/')
    args=parser.parse_args()
    print(asyncio.run(search(args.query,args.url,os.getenv('RETRIEVAL_API_TOKEN',''))).model_dump_json(indent=2))

if __name__ == '__main__':
    main()
