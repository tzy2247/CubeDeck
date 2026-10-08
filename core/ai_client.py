"""OpenAI 兼容 API 客户端（零依赖，用 urllib）。"""
import json
import urllib.request
import urllib.error


class AIClient:
    def __init__(self, base_url, api_key, model, timeout=30):
        self.base_url = (base_url or "").rstrip("/")
        self.api_key = api_key or ""
        self.model = model or ""
        self.timeout = timeout

    def chat(self, messages, temperature=0.7, max_tokens=400):
        """发送 chat completion。返回 (回复文本, 错误信息)。"""
        if not self.base_url:
            return None, "未配置 API 网址"
        if not self.model:
            return None, "未配置模型名"

        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        try:
            body = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                url, data=body, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            content = data["choices"][0]["message"]["content"]
            return content, None
        except urllib.error.HTTPError as e:
            try:
                err = e.read().decode("utf-8")
            except Exception:
                err = str(e)
            return None, f"HTTP {e.code}: {err[:200]}"
        except Exception as e:
            return None, str(e)

    def test_connection(self):
        reply, err = self.chat(
            [{"role": "user", "content": "Reply with the single word: ok"}],
            temperature=0.0, max_tokens=10)
        if err:
            return False, err
        return True, f"连接正常 · 回复：{(reply or '')[:40]}"