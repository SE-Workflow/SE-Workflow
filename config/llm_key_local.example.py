"""本地大模型密钥配置模板。

复制本文件为 config/llm_key_local.py 后填写真实值；
llm_key_local.py 已被 .gitignore 忽略，不会被提交。
环境变量优先级高于本文件（见 config/llm_key.py）。
"""

MODE = "openai"
BASE_URL = "https://api.openai.com/v1"
API_KEY = "sk-your-key"
MODEL = "gpt-4o-mini"
TIMEOUT = 20
