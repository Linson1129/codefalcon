"""配置管理 - 从环境变量和配置文件加载设置"""

import os
import logging
from functools import lru_cache
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class Config:
    """全局配置管理器"""

    # API 配置映射
    API_CONFIG = {
        "deepseek-chat": {
            "api_key_env": "DEEPSEEK_API_KEY",
            "base_url_env": "DEEPSEEK_BASE_URL",
            "default_base": "https://api.deepseek.com",
        },
        "qwen-turbo": {
            "api_key_env": "QWEN_API_KEY",
            "base_url_env": "QWEN_BASE_URL",
            "default_base": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        },
    }

    def get_api_key(self, model: str) -> str:
        """获取指定模型的API Key"""
        if model in self.API_CONFIG:
            env_var = self.API_CONFIG[model]["api_key_env"]
            key = os.getenv(env_var, "")
            if not key:
                logger.warning(f"[Config] {env_var} 未设置，请在 .env 文件中配置")
            return key
        return os.getenv("OPENAI_API_KEY", "")

    def get_api_base(self, model: str) -> str:
        """获取指定模型的API Base URL"""
        if model in self.API_CONFIG:
            env_var = self.API_CONFIG[model]["base_url_env"]
            return os.getenv(env_var, self.API_CONFIG[model]["default_base"])
        return os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")

    def get_timeout(self) -> int:
        """LLM调用超时（秒）"""
        return int(os.getenv("CODEFALCON_TIMEOUT", str(self.DEFAULT_TIMEOUT)))

    # ---- 集中管理的常量 ----

    DEFAULT_TIMEOUT: int = 60
    MAX_RETRIES: int = 3
    LLM_TEMPERATURE: float = 0.1
    REVIEW_WINDOW: int = 10  # 滚动窗口保留报告数
    MAX_LINE_LENGTH: int = 120
    SPEC_TRUNCATE_CHARS: int = 4000
    MCP_HTTP_PORT: int = 8765
    DEPENDENCY_DISPLAY_LIMIT: int = 5  # prompt 中显示依赖模块数
    DEFAULT_MAX_TOKENS: int = 50000  # 单次审查 Token 预算上限

    def get_max_tokens(self) -> int:
        """LLM 调用的 Token 预算上限"""
        return int(os.getenv("CODEFALCON_MAX_TOKENS", str(self.DEFAULT_MAX_TOKENS)))


@lru_cache()
def get_config() -> Config:
    """获取配置单例"""
    return Config()
