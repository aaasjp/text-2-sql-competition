import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

WORKING_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = WORKING_DIR.parent

load_dotenv(WORKING_DIR / ".env")
load_dotenv(PROJECT_ROOT / ".env")

API_KEY = os.environ.get("API_KEY") or os.environ.get("DEEPSEEK_API_KEY")
BASE_URL = (
    os.environ.get("BASE_URL")
    or os.environ.get("DEEPSEEK_BASE_URL")
    or "https://api.deepseek.com"
)
MODEL = os.environ.get("MODEL") or "DeepSeek-V4-Flash"

if not API_KEY:
    raise SystemExit("未找到 API Key，请在 working/.env 中配置 API_KEY")

client = OpenAI(api_key=API_KEY, base_url=BASE_URL)
messages = [{"role": "user", "content": "What is 17*19? Return only the final integer."}]

# Non-think
resp = client.chat.completions.create(
    model=MODEL,
    messages=messages,
)
print("Non-think:", resp.choices[0].message.content)

# Think High
resp = client.chat.completions.create(
    model=MODEL,
    messages=messages,
    extra_body={
        "chat_template_kwargs": {
            "thinking": True,
            "reasoning_effort": "high",
        },
    },
)
print("Think High content:", resp.choices[0].message.content)
print("Think High reasoning:", getattr(resp.choices[0].message, "reasoning", None))

# Think Max
resp = client.chat.completions.create(
    model=MODEL,
    messages=messages,
    extra_body={
        "chat_template_kwargs": {
            "thinking": True,
            "reasoning_effort": "max",
        },
    },
)
print("Think Max content:", resp.choices[0].message.content)
print("Think Max reasoning:", getattr(resp.choices[0].message, "reasoning", None))
