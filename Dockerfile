FROM python:3.11-slim

WORKDIR /app

# 安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制项目文件
COPY pyproject.toml .
COPY src/ ./src/

# 安装为可执行命令
RUN pip install --no-cache-dir -e .

# 创建输出目录
RUN mkdir -p reviews

# 默认入口
ENTRYPOINT ["codefalcon"]
CMD ["--help"]
