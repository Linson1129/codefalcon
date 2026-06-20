# 测试样本：包含安全问题的代码

import os

# 硬编码密钥（应被检测）
API_KEY = "sk-proj-this-is-a-fake-key-for-testing"
SECRET_TOKEN = "ghp_this_is_a_fake_github_token_for_test"

# 硬编码密码（应被检测）
DB_PASSWORD = "admin123"


def get_user_by_name(name):
    # SQL注入风险（应被检测）
    query = "SELECT * FROM users WHERE name = '" + name + "'"
    return query


def delete_user_input(user_input):
    # 命令注入风险（应被检测）
    os.system("rm -rf /tmp/" + user_input)


def unsafe_eval(code):
    # eval风险（应被检测）
    return eval(code)


def good_function(a: int, b: int) -> int:
    """正常函数，不应被标记"""
    return a + b
