# 测试样本：干净的代码

import hashlib
import os
from typing import Optional


def hash_password(password: str) -> str:
    """安全地对密码进行哈希"""
    salt = os.urandom(16)
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode(), salt, 100000
    ).hex()


def find_user(user_id: int) -> Optional[dict]:
    """使用参数化查询安全查找用户"""
    # 注意：这里只是示例，实际应使用数据库参数化查询
    query = "SELECT * FROM users WHERE id = ?"
    return {"query": query, "id": user_id}


def calculate_discount(price: float, membership_level: int) -> float:
    """计算折扣"""
    rates = {1: 0.05, 2: 0.10, 3: 0.15}
    rate = rates.get(membership_level, 0.0)
    return price * (1 - rate)


class UserService:
    """用户服务类"""

    def __init__(self):
        self._users = {}

    def add_user(self, name: str, email: str) -> int:
        """添加用户"""
        user_id = len(self._users) + 1
        self._users[user_id] = {
            "id": user_id,
            "name": name,
            "email": email,
        }
        return user_id

    def get_user(self, user_id: int) -> Optional[dict]:
        """获取用户"""
        return self._users.get(user_id)
