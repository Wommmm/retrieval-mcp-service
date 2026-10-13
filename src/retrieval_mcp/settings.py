import os
from pydantic import BaseModel, Field
from typing import Literal

class Settings(BaseModel):
    backend: Literal['demo', 'live'] = 'demo'
    request_timeout: float = Field(default=90, gt=0, le=600)
    max_workers: int = Field(default=1, ge=1, le=8)
    max_pending: int = Field(default=4, ge=1, le=32)
    cache_ttl: float = Field(default=60, ge=0, le=3600)
    cache_entries: int = Field(default=128, ge=0, le=10000)
    corpus_version: str = 'rs12-v1'
    api_token: str = Field(default='', repr=False)

    @classmethod
    def from_env(cls):
        mapping = {name: os.environ['RETRIEVAL_'+name.upper()]
                   for name in cls.model_fields if 'RETRIEVAL_'+name.upper() in os.environ}
        return cls(**mapping)
