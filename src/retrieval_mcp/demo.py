"""Deterministic fixture for protocol demos. Not Milvus/BGE quality evidence."""
import hashlib
from .contracts import Document, SearchResult, StageTrace

class DemoBackend:
    records = [
        ('电池 battery', 'RS-12 数字万用表使用 9V NEDA 1604 电池。'),
        ('温度 temperature', '操作温度：0°C ~ 50°C（32°F ~ 122°F）。'),
        ('保持 hold 读数', '按下“HOLD”键保持读数。'),
        ('ol 超出', '显示 OL 表示测量值超出所选档位。'),
        ('电阻 断电', '测量前应断开电源，并给电容充分放电。'),
    ]

    def retrieve(self, request, execution_id):
        query = request.query.lower()
        found = [(tags, text) for tags,text in self.records if any(t in query for t in tags.split())]
        documents = [Document(id=hashlib.sha256(text.encode()).hexdigest()[:16],
            content=text, source='demo', title='RS-12 protocol demo fixture', score=1,
            score_type='lexical') for _,text in found[:request.top_k]]
        return SearchResult(request_id=execution_id, execution_id=execution_id, backend='demo',
            status='ok' if documents else 'empty', documents=documents,
            warnings=['demo_fixture_not_real_retrieval'],
            traces=[StageTrace(stage='demo_lexical', status='ok' if documents else 'empty',
                duration_ms=0, documents=len(documents))])
