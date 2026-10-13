"""Actual SDK initialize/list_tools/call_tool over a temporary local HTTP server."""
import asyncio
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from retrieval_mcp.client import search

def test_mcp_discovery_call_and_errors(tmp_path, monkeypatch):
    monkeypatch.setenv('NO_PROXY','127.0.0.1,localhost')
    with socket.socket() as reservation:
        reservation.bind(('127.0.0.1',0))
        port=reservation.getsockname()[1]
    env=dict(os.environ,RETRIEVAL_BACKEND='demo',RETRIEVAL_API_TOKEN='',PYTHONPATH=str(Path('src').resolve()))
    log=(tmp_path/'server.log').open('w')
    process=subprocess.Popen([sys.executable,'-m','retrieval_mcp','--port',str(port),'--env-file',str(tmp_path/'missing')],
        env=env,stdout=log,stderr=log)
    url=f'http://127.0.0.1:{port}'
    try:
        with httpx.Client(trust_env=False) as client:
            for _ in range(100):
                try:
                    if client.get(url+'/health/live').status_code==200: break
                except httpx.ConnectError:
                    time.sleep(.05)
            else: raise AssertionError('Temporary MCP server failed to start')
        async def check():
            async with streamable_http_client(url+'/mcp/') as (read,write,_):
                async with ClientSession(read,write) as session:
                    await session.initialize()
                    listing=await session.list_tools()
                    tool=next(t for t in listing.tools if t.name=='search_knowledge')
                    assert 'query' in tool.inputSchema['properties']
                    assert tool.outputSchema
                    reply=await session.call_tool('search_knowledge',{'query':'电池'})
                    assert not reply.isError
                    assert reply.structuredContent['documents'][0]['source']=='demo'
                    error=await session.call_tool('search_knowledge',{'query':' '})
                    assert error.isError
            result=await search('no evidence',url+'/mcp/')
            assert result.status=='empty' and result.documents==[]
        asyncio.run(check())
    finally:
        process.terminate()
        process.wait(timeout=15)
        log.close()
