# 检索接口契约

HTTP 和 MCP 使用同一 Pydantic `SearchResult`，避免不同入口分别解释检索结果。

| 情况 | HTTP | 结果或错误 |
|---|---|---|
| 找到文档 | 200 | status=ok，documents 非空 |
| 未找到文档 | 200 | status=empty，documents=[] |
| 商品不明确 | 200 | status=clarification，message 提示补充，documents=[] |
| 可选 HyDE/KG/Web 故障 | 200 | status=partial，warnings 和 traces 标明失败路线，保留可用文档 |
| 商品识别、向量或精排故障 | 503 | error.code 与 request_id |
| 待处理执行任务过多 | 429 | capacity_exceeded，Retry-After=5 |
| 当前调用等待超过时限 | 504 | retrieval_timeout，后台容量继续占用 |
| query 缺失、空白或参数越界 | 422 | 请求校验错误 |
| 配置 token 后认证失败 | 401 | unauthorized |

MCP 在正常情况下通过 structuredContent 返回同一模型；工具失败时 isError=True，内容提供错误码和请求 ID。传输层 HTTP 状态与 MCP 工具状态是不同层次，客户端两者都要处理。客户端管理 AsyncClient、传输流和 ClientSession 的关闭。

`request_id` 每次请求不同；共享任务或缓存命中保留原 `execution_id`。`duration_ms` 是本次调用等待时间，`execution_ms` 是后端执行时间，`traces` 是原检索的阶段信息。缓存命中时 traces 不代表本次又执行了这些阶段。

`backend=demo` 的记录明确标记 source=demo，并给 warning；不能用于真实检索准确率。`backend=live` 文档来源是既有 Milvus 集合或外部 MCP 网页搜索。HyDE 生成文本仅辅助召回，不当作来源文档返回。

同题合并仅在 use_cache=True 时启用。缓存范围为单进程、单知识库，不包含用户权限；不同权限知识库应使用不同服务实例或扩展隔离键后再使用。当前不宣称支持多租户。
