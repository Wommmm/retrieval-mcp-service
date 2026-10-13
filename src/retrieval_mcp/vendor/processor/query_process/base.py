"""Standalone node contract adapted from the preserved teaching baseline.

Task tracking, SSE and conversation persistence belong to the consumer, not retrieval.
"""
from abc import ABC, abstractmethod
import logging
from typing import TypeVar
from .config import get_config

T = TypeVar('T')

class BaseNode(ABC):
    name = 'base_node'

    def __init__(self, config=None):
        self.config = config or get_config()
        self.logger = logging.getLogger(f'retrieval.node.{self.name}')

    def __call__(self, state):
        return self.process(state)

    @abstractmethod
    def process(self, state):
        raise NotImplementedError

    def log_step(self, step_name, message=''):
        self.logger.debug('%s', step_name)

def setup_logging(level=logging.INFO):
    logging.basicConfig(level=level)
