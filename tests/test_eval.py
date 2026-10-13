import importlib.util
from pathlib import Path
import pytest

spec=importlib.util.spec_from_file_location('evaluation',Path('scripts/evaluate.py'))
evaluation=importlib.util.module_from_spec(spec)
spec.loader.exec_module(evaluation)

@pytest.mark.parametrize('docs,terms,k,hit,rr',[
    ([],['battery'],3,False,0),
    ([{'content':'other'},{'content':'battery'}],['battery'],1,False,.5),
    ([{'content':'battery'}],['battery'],3,True,1),
])
def test_content_metrics(docs,terms,k,hit,rr):
    result=evaluation.score(docs,terms,k)
    assert result['hit_at_k']==hit
    assert result['reciprocal_rank']==rr
