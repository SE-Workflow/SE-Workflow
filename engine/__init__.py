"""SE Workflow 引擎包。

对外只暴露一个入口：`analyze(requirement)`，返回可直接 JSON 化的编排方案。
"""

from .pipeline import analyze

__all__ = ["analyze"]
