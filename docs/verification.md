# 工程验证 2026年10月13日

## 接口与安装

实际运行完整本地测试：20项通过，1条SDK/Pydantic警告。包含参数、正常/空结果、异常脱敏、认证、TTL、任务共享、深复制、容量和超时占位、降级不缓存、配置缓存键、图路径、过滤转义、MCP实际HTTP传输及评测指标。图测试使用替换依赖，不能代表真实模型准确率。

构建wheel并安装到独立目录，阻断原knowledge包导入后接口仍可运行，demo没有导入torch/pymilvus/neo4j。最终安装包另行启动，HTTP200和MCP SDK均返回文档。Docker镜像也实际构建并启动，非root运行，HTTP200、backend=demo。Docker和demo证明运行及协议，不代表live质量。

## 相同5题的真实检索配置对比

固定top_k=5、禁用缓存，使用RS-12说明书已有Milvus索引、Neo4j、本地CPU BGE与实际LLM、可选外部搜索。每种模式运行5题，共20次请求，均HTTP200且无partial。

| 配置 | HTTP成功 | Hit@5 | MRR | 平均耗时秒 |
|---|---|---|---|---|
| 向量 | 5/5 | 0.60 | 0.600 | 3.284 |
| 向量加HyDE加KG后RRF | 5/5 | 1.00 | 0.717 | 5.969 |
| 本地融合加BGE精排 | 5/5 | 1.00 | 0.767 | 23.247 |
| 加联网后精排 | 5/5 | 0.80 | 0.550 | 29.831 |

默认采用本地融合精排，联网保留为选项。原始结果见 `reports/live-ablation.json`，保留全部文档、未命中与耗时。该小样本为精确内容子串标签，不能推广成其他知识库或业务准确率；LLM改写有不确定性，耗时包含初始化与请求差异，没有多次重复或负载压测，不声称通用性能提升。

## 真实最小Agent消费

真实LLM→ToolNode→MCP Client→独立Server→live检索→ToolMessage→LLM。电池问题：1次工具调用、3条文档、1条ToolMessage、35.141秒，回答9V NEDA1604并给出真实文档标题和切片ID。见 `reports/live-mcp-agent.json`。

这是最小消费方示例，未验证整个Supervisor平台，也不包含Safeguard。服务与消费方验证环境分别记录在 `verified-runtime.json` 和 `agent-runtime.json`；原始环境未被升级或覆盖。

## 边界与发布

单进程缓存与容量，CPU路线顺序执行，超时不强制终止同步推理。复用已有索引，没有重新验收完整上传/导入。模拟测试、demo、真实HTTP和真实Agent报告分别标记。

发布源码使用全新Git历史，保留源码来源而排除旧配置历史。发布前扫描源码、历史和实际私密值，检查.env与打包排除规则。持续集成配置包含只读权限、固定Actions提交及密钥扫描；远端运行结果以GitHub Actions页面为准。
