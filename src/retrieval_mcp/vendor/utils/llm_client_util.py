import os, logging

logger = logging.getLogger(__name__)
# Logging is configured by the service entry point.

from langchain_openai import ChatOpenAI
from dotenv import load_dotenv

# Environment is loaded explicitly at service startup.

cache_llm_client = {}


def get_llm_client(mode_name: str = None, temperature: float = 0.0, response_format: bool = False):
    """

    Returns: 返回LLM客户端对象
    # 自己加的提供:dashscope
    # 兼容OpenAI: LangChain LangGraph(集成OpenAI)
    缓存的对象是：client
    缓存的key: 不同的节点用不同的模型以及同一个节点用不同响应格式
    """

    # 1. 获取模型的名字
    model_name = mode_name or os.getenv('ITEM_MODEL', "qwen-flash")
    api_key = (
        os.getenv("new_apikey")
        or os.getenv("DASHSCOPE_API_KEY")
        or os.getenv("OPENAI_API_KEY")
    )
    if not api_key:
        raise ValueError(
            "请设置环境变量 new_apikey、DASHSCOPE_API_KEY 或 OPENAI_API_KEY"
        )
    api_base = os.getenv(
        "OPENAI_API_BASE",
        "https://dashscope.aliyuncs.com/compatible-mode/v1",
    )

    cache_key = (model_name, api_base, api_key, temperature, response_format)  # 复合缓存key(a,b)

    # 2. 缓存命中 直接返回
    if cache_key in cache_llm_client:
        return cache_llm_client[cache_key]

    # 3. 返回的内容格式
    model_kwargs = {}
    if response_format:
        model_kwargs['response_format'] = {"type": "json_object"}
    try:
        # 4. 定义模型实例
        client = ChatOpenAI(
            model_name=model_name,
            openai_api_key=api_key,
            openai_api_base=api_base,
            temperature=temperature,
            extra_body={"enable_thinking": False},
            model_kwargs=model_kwargs, timeout=25, max_retries=0
        )

        # 5. 同步数据
        cache_llm_client[cache_key] = client

        # 6. 返回
        return client
    except Exception as e:
        logger.error(f"LLM客户端创建失败,原因:{str(e)}")
        return None


