"""Real small Agent consuming the independent service. Leaves project two untouched."""
import argparse
import asyncio
import json
import os
from pathlib import Path
from time import monotonic
from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.graph import StateGraph, MessagesState, START, END
from langgraph.prebuilt import ToolNode
from retrieval_mcp.client import search

async def run(query, url):
    from retrieval_mcp.vendor.utils.llm_client_util import get_llm_client
    model=get_llm_client()
    calls=[]

    @tool
    async def knowledge_search(query: str) -> str:
        """检索产品说明书。返回来源文档、status与warnings；资料不足时不能编造答案。"""
        result=await search(query,url,os.getenv('RETRIEVAL_API_TOKEN',''))
        calls.append(result.model_dump())
        return result.model_dump_json()

    async def model_node(state):
        rounds=sum(isinstance(m,AIMessage) and bool(m.tool_calls) for m in state['messages'])
        target=model.bind_tools([knowledge_search]) if rounds<2 else model
        response=await target.ainvoke([SystemMessage(content=(
            '你是产品说明书助手。先调用knowledge_search获取资料，再仅根据相关文档简短回答。'
            '引用来源标题和chunk_id，不编造链接。empty说明资料不足；partial说明部分检索失败；'
            'clarification请用户补充产品名称。'))]+state['messages'])
        return {'messages':[response]}

    graph=StateGraph(MessagesState)
    graph.add_node('model',model_node)
    graph.add_node('tools',ToolNode([knowledge_search],handle_tool_errors=lambda error:'检索暂时不可用'))
    graph.add_edge(START,'model')
    graph.add_conditional_edges('model',lambda state:'tools' if state['messages'][-1].tool_calls else 'done',
        {'tools':'tools','done':END})
    graph.add_edge('tools','model')
    started=monotonic()
    result=await graph.compile().ainvoke({'messages':[HumanMessage(content=query)]},config={'recursion_limit':12})
    return {'source':'real_llm_agent_to_independent_mcp', 'query':query,
        'latency_s':round(monotonic()-started,3),'tool_calls':calls,
        'tool_message_count':sum(isinstance(m,ToolMessage) for m in result['messages']),
        'answer':result['messages'][-1].content,
        'limitations':['Single case integration, not a quality benchmark.',
            'Minimal consumer example, not the full original Supervisor platform.',
            'No Safeguard component in this example.']}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--query',default='RS-12数字万用表使用什么电池？')
    parser.add_argument('--url',default='http://127.0.0.1:8050/mcp/')
    parser.add_argument('--output',type=Path,default=Path('reports/live-mcp-agent.json'))
    args=parser.parse_args()
    load_dotenv('.env',override=False)
    report=asyncio.run(run(args.query,args.url))
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    assert report['tool_calls'] and all(c['backend']=='live' for c in report['tool_calls'])
    assert report['answer']
    print(json.dumps({'tool_calls':len(report['tool_calls']),'tool_messages':report['tool_message_count'],
        'latency_s':report['latency_s'],'documents':[len(c['documents']) for c in report['tool_calls']],
        'answer':report['answer']},ensure_ascii=False,indent=2))

if __name__=='__main__':
    main()
