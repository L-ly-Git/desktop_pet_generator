# -*- coding: utf-8 -*-
"""AI 对话引擎：OpenAI 兼容接口（智谱/DeepSeek/Ollama/OpenAI 等）。

- 只用 requests，不引入新依赖。
- 网络请求在后台线程，通过 pyqtSignal 回到主线程，不阻塞 Qt 主循环。
- 系统提示词 = persona(name+setting) + 知识库(key-value) 注入。
- 回复可选带动作标签 [wave] / [jump] / [nod] ...，用于触发动作。
"""
from __future__ import annotations

import json
import os
import re
import threading
from pathlib import Path

from PyQt5.QtCore import QObject, pyqtSignal

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None

ROOT = Path(__file__).resolve().parents[1]
try:
    from app_paths import data_root
    CONFIG_PATH = data_root() / "runtime" / "chat_config.json"
except Exception:  # pragma: no cover
    CONFIG_PATH = ROOT / "runtime" / "chat_config.json"

# 动作标签：动态读取动作库（新加的动作 AI 也能用 [id] 触发）
def load_action_tags() -> list[str]:
    try:
        from app_paths import actions_dir
        d = actions_dir()
        if d.is_dir():
            tags = sorted(p.stem for p in d.glob("*.json"))
            if tags:
                return tags
    except Exception:  # noqa: BLE001
        pass
    return ["wave", "jump", "nod", "shake_head", "yawn", "blink", "walk", "idle_breath"]


ACTION_TAGS = load_action_tags()
# 情绪词 -> 动作
EMOTION_TO_ACTION = {
    "happy": "wave", "开心": "wave", "高兴": "wave", "兴奋": "jump",
    "surprise": "jump", "惊讶": "jump", "吃惊": "jump",
    "think": "nod", "思考": "nod", "疑惑": "nod",
    "shy": "blink", "害羞": "blink", "卖萌": "blink", "可爱": "blink",
    "calm": "idle_breath", "平静": "idle_breath", "普通": "idle_breath",
    "tired": "yawn", "困": "yawn", "累": "yawn",
    "no": "shake_head", "否定": "shake_head", "摇头": "shake_head",
}

DEFAULT_CONFIG = {
    "base_url": "https://open.bigmodel.cn/api/paas/v4",
    "model": "glm-4-flash",
    "api_key": "",
    "timeout": 20,
    "history_turns": 8,
    "max_chars": 40,
    "fallback": "我现在连不上网……",
}

_TAG_RE = re.compile(r"^\s*[\[【]\s*([A-Za-z_\u4e00-\u9fff]+)\s*[\]】]\s*")


def load_config() -> dict:
    cfg = dict(DEFAULT_CONFIG)
    try:
        if CONFIG_PATH.exists():
            cfg.update(json.loads(CONFIG_PATH.read_text(encoding="utf-8-sig")))
    except (OSError, ValueError):
        pass
    cfg["base_url"] = os.environ.get("AI_BASE_URL", cfg.get("base_url", ""))
    cfg["api_key"] = os.environ.get("AI_API_KEY", cfg.get("api_key", ""))
    cfg["model"] = os.environ.get("AI_MODEL", cfg.get("model", ""))
    return cfg


def build_system_prompt(persona: dict, knowledge: list) -> str:
    """把 persona + 知识库注入系统提示词。"""
    name = (persona or {}).get("name", "桌宠").strip() or "桌宠"
    setting = (persona or {}).get("setting", "").strip()
    parts = [f"你是 {name}，一只住在电脑桌面上的 Q 版桌宠。"]
    if setting:
        parts.append(f"人设：{setting}")
    if knowledge:
        lines = ["知识库："]
        for item in knowledge:
            if isinstance(item, dict) and str(item.get("key", "")).strip():
                lines.append(f"- {item['key']}：{item['value']}")
        parts.append("\n".join(lines))
    parts.append(
        "回答要求：简短、口语化、可爱；总长度不超过 " +
        f"{load_config().get('max_chars', 40)} 字。"
        "如果想配合动作，在回复最前面加一个动作标签，可选："
        + " ".join(f"[{t}]" for t in ACTION_TAGS) + "。"
    )
    parts.append(
        "重要：你只能依据上面的人设、知识库以及当前对话历史来回答，"
        "绝对不要编造不存在的事实、人物关系或知识；"
        "如果用户问的内容在知识库和历史里都没有，就诚实说还不清楚，不要乱猜。"
    )
    return "\n\n".join(parts)


def parse_reply(raw: str) -> tuple[str, str | None]:
    """从回复开头提取动作/情绪标签，返回 (纯文本, action_id)。"""
    text = (raw or "").strip()
    action = None
    m = _TAG_RE.match(text)
    if m:
        tag = m.group(1)
        text = text[m.end():].strip()
        if tag in ACTION_TAGS:
            action = tag
        elif tag in EMOTION_TO_ACTION:
            action = EMOTION_TO_ACTION[tag]
    return text, action


class AIClient(QObject):
    """后台线程调用 OpenAI 兼容接口，结果通过信号回主线程。"""

    reply_ready = pyqtSignal(str, str)   # (回复文本, action_id 或 "")
    reply_failed = pyqtSignal(str)       # (兜底文案)

    def __init__(self, config: dict | None = None, persona: dict | None = None,
                 knowledge: list | None = None, history_path: Path | None = None,
                 memory_path: Path | None = None):
        super().__init__()
        self.config = config or load_config()
        self.persona = persona or {}
        self.knowledge = knowledge or []   # character.json 的知识库（用户维护）
        self.history_path = history_path
        self.memory_path = memory_path
        self.history: list[dict] = self._load_history()  # 对话历史
        self.memory: list[dict] = self._load_memory()    # 从对话提取的事实
        self.system_prompt = self._build_prompt()

    # ---------- 调用 ----------
    def ask(self, user_text: str) -> None:
        if not requests or not self.config.get("api_key"):
            self.reply_failed.emit(self.config.get("fallback", "我现在连不上网……"))
            return
        thread = threading.Thread(target=self._run, args=(user_text,), daemon=True)
        thread.start()

    def _run(self, user_text: str) -> None:
        try:
            raw = self._call_api(user_text)
            text, action = parse_reply(raw)
            if not text:
                text = raw
            self.reply_ready.emit(text, action or "")
        except Exception:
            self.reply_failed.emit(self.config.get("fallback", "我现在连不上网……"))
            return
        # 回复之后，后台提取并更新记忆（失败不影响回复）
        try:
            self._update_memory(user_text)
        except Exception:
            pass

    def _call_api(self, user_text: str) -> str:
        messages = [{"role": "system", "content": self.system_prompt}]
        turns = max(0, int(self.config.get("history_turns", 8)))
        messages.extend(self.history[-turns * 2:])
        messages.append({"role": "user", "content": user_text})
        url = self.config["base_url"].rstrip("/") + "/chat/completions"
        headers = {"Authorization": f"Bearer {self.config['api_key']}"}
        payload = {
            "model": self.config["model"],
            "messages": messages,
            "temperature": 0.9,
        }
        resp = requests.post(url, headers=headers, json=payload,
                             timeout=float(self.config.get("timeout", 20)))
        resp.raise_for_status()
        data = resp.json()
        reply = data["choices"][0]["message"]["content"].strip()
        # 记录历史（只记纯文本，不含动作标签）
        text, _ = parse_reply(reply)
        self.history.append({"role": "user", "content": user_text})
        self.history.append({"role": "assistant", "content": text})
        self._save_history()
        return reply

    def reset(self) -> None:
        self.history.clear()
        self._save_history()

    # ---------- 长时记忆 ----------
    def _load_history(self) -> list[dict]:
        if self.history_path is None or not self.history_path.exists():
            return []
        try:
            data = json.loads(self.history_path.read_text(encoding="utf-8-sig"))
            if isinstance(data, list):
                return [m for m in data if isinstance(m, dict) and m.get("role") in ("user", "assistant")]
        except (OSError, ValueError):
            return []
        return []

    def _save_history(self) -> None:
        if self.history_path is None:
            return
        try:
            self.history_path.parent.mkdir(parents=True, exist_ok=True)
            self.history_path.write_text(
                json.dumps(self.history, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        except OSError:
            pass

    def _build_prompt(self) -> str:
        return build_system_prompt(self.persona, self.knowledge + self.memory)

    def _load_memory(self) -> list[dict]:
        if self.memory_path is None or not self.memory_path.exists():
            return []
        try:
            data = json.loads(self.memory_path.read_text(encoding="utf-8-sig"))
            if isinstance(data, list):
                return [m for m in data if isinstance(m, dict) and str(m.get("key", "")).strip()]
        except (OSError, ValueError):
            return []
        return []

    def _save_memory(self) -> None:
        if self.memory_path is None:
            return
        try:
            self.memory_path.parent.mkdir(parents=True, exist_ok=True)
            self.memory_path.write_text(
                json.dumps(self.memory, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        except OSError:
            pass

    def _extract_facts(self, user_text: str) -> list[dict]:
        if not requests or not self.config.get("api_key"):
            return []
        url = self.config["base_url"].rstrip("/") + "/chat/completions"
        headers = {"Authorization": f"Bearer {self.config['api_key']}"}
        prompt = (
            "从下面这句话里提取用户明确表达的事实（喜好、人物关系、身份、称呼等），"
            "输出 JSON 数组，每项包含 key 和 value 两个字段。"
            "只提取明确陈述，不要推断或编造；如果没有新事实，输出空数组 []。"
            "只输出 JSON 数组本身，不要任何多余文字。 "
            f"用户的话：{user_text}"
        )
        payload = {
            "model": self.config["model"],
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
        }
        resp = requests.post(url, headers=headers, json=payload,
                             timeout=float(self.config.get("timeout", 20)))
        resp.raise_for_status()
        reply = resp.json()["choices"][0]["message"]["content"].strip()
        reply = re.sub(r"```(?:json)?|```", "", reply).strip()
        match = re.search(r"\[.*\]", reply, re.S)
        data = json.loads(match.group(0) if match else reply)
        if not isinstance(data, list):
            return []
        facts = []
        for item in data:
            if isinstance(item, dict):
                k = str(item.get("key", "")).strip()
                v = str(item.get("value", "")).strip()
                if k and v:
                    facts.append({"key": k, "value": v})
        return facts

    def _update_memory(self, user_text: str) -> None:
        facts = self._extract_facts(user_text)
        if not facts:
            return
        known = {}
        for item in self.memory:
            if isinstance(item, dict) and str(item.get("key", "")).strip():
                known[str(item["key"]).strip()] = str(item.get("value", "")).strip()
        for f in facts:
            k = str(f.get("key", "")).strip()
            v = str(f.get("value", "")).strip()
            if k and v:
                known[k] = v
        self.memory = [{"key": k, "value": v} for k, v in known.items()]
        self._save_memory()
        self.system_prompt = self._build_prompt()

    def clear_history(self) -> None:
        """清空对话记忆与提取的事实（内存 + 磁盘文件）。"""
        self.history.clear()
        self.memory.clear()
        if self.history_path is not None:
            try:
                if self.history_path.exists():
                    self.history_path.unlink()
            except OSError:
                pass
        if self.memory_path is not None:
            try:
                if self.memory_path.exists():
                    self.memory_path.unlink()
            except OSError:
                pass
        self.system_prompt = self._build_prompt()
