"""
llm_client.py — FluidVoice Windows
Unified completions client for OpenAI, Groq, and Custom (Ollama) endpoints.
Supports streaming, thinking token extraction, and tool call reconstruction.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any, Callable, Generator, Optional
import httpx

from settings import settings


class LLMError(Exception):
    """Custom exception class for LLMClient errors."""
    pass


class ToolCall:
    """Represents a tool call request from the LLM."""
    def __init__(self, call_id: str, name: str, arguments: dict[str, Any]) -> None:
        self.id = call_id
        self.name = name
        self.arguments = arguments

    def get_string(self, key: str) -> Optional[str]:
        return self.arguments.get(key)

    def get_optional_string(self, key: str) -> Optional[str]:
        val = self.arguments.get(key)
        return val if val and str(val).strip() else None

    @classmethod
    def from_dict(cls, d: dict) -> ToolCall:
        return cls(
            call_id=d.get("id", ""),
            name=d.get("name", ""),
            arguments=d.get("arguments", {})
        )


class LLMResponse:
    """Unified response object returned by LLMClient."""
    def __init__(
        self,
        content: str,
        thinking: Optional[str] = None,
        tool_calls: list[ToolCall] = None
    ) -> None:
        self.content = content
        self.thinking = thinking
        self.tool_calls = tool_calls or []


class LLMClient:
    """Communicates with OpenAI-compatible API endpoints."""

    @staticmethod
    def call(
        messages: list[dict[str, Any]],
        provider: str,
        model: str,
        api_key: str,
        base_url: str = "",
        streaming: bool = False,
        tools: Optional[list[dict[str, Any]]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        on_content_chunk: Optional[Callable[[str], None]] = None,
        on_thinking_chunk: Optional[Callable[[str], None]] = None,
    ) -> LLMResponse:
        """
        Execute a chat completion request (blocking or streaming).
        Raises LLMError on failure.
        """
        # Resolve endpoint URL
        url = base_url.strip()
        if not url:
            if provider == "openai":
                url = "https://api.openai.com/v1"
            elif provider == "groq":
                url = "https://api.groq.com/openai/v1"
            else:
                url = "http://localhost:11434/v1" # Local Ollama default

        endpoint = f"{url}/chat/completions"

        # Headers
        headers = {
            "Content-Type": "application/json"
        }
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        # Payload
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": streaming
        }
        if temperature is not None:
            payload["temperature"] = temperature
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        # Handle model-specific reasoning configs
        model_lower = model.lower()
        if "nemotron" in model_lower or "nemo" in model_lower:
            payload["enable_thinking"] = True
        elif "deepseek" in model_lower and "r1" in model_lower:
            payload["enable_reasoning"] = True

        try:
            if streaming:
                return LLMClient._execute_streaming(
                    endpoint, headers, payload, on_content_chunk, on_thinking_chunk
                )
            else:
                return LLMClient._execute_non_streaming(endpoint, headers, payload)
        except Exception as e:
            if isinstance(e, LLMError):
                raise e
            raise LLMError(f"HTTP request failed: {e}")

    @staticmethod
    def _execute_non_streaming(endpoint: str, headers: dict[str, str], payload: dict[str, Any]) -> LLMResponse:
        with httpx.Client(timeout=60.0) as client:
            resp = client.post(endpoint, headers=headers, json=payload)
            if resp.status_code >= 400:
                raise LLMError(f"HTTP {resp.status_code}: {resp.text}")

            data = resp.json()
            choices = data.get("choices", [])
            if not choices:
                raise LLMError("API returned an empty response choices list")

            message = choices[0].get("message", {})
            content = message.get("content") or ""
            
            # Extract reasoning/thinking from field or tags
            thinking = message.get("reasoning_content") or message.get("reasoning")
            if not thinking:
                # Fallback to <think> tag search
                think_match = re.search(r"<think>(.*?)</think>", content, re.DOTALL | re.IGNORECASE)
                if think_match:
                    thinking = think_match.group(1).strip()
                    content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL | re.IGNORECASE).strip()

            # Parse tool calls
            tool_calls = []
            raw_calls = message.get("tool_calls", [])
            for rc in raw_calls:
                fn = rc.get("function", {})
                args_str = fn.get("arguments", "{}")
                try:
                    args = json.loads(args_str)
                except Exception:
                    args = {}
                tool_calls.append(ToolCall(
                    call_id=rc.get("id", ""),
                    name=fn.get("name", ""),
                    arguments=args
                ))

            return LLMResponse(content=content, thinking=thinking, tool_calls=tool_calls)

    @staticmethod
    def _execute_streaming(
        endpoint: str,
        headers: dict[str, str],
        payload: dict[str, Any],
        on_content_chunk: Optional[Callable[[str], None]],
        on_thinking_chunk: Optional[Callable[[str], None]]
    ) -> LLMResponse:
        content_parts = []
        thinking_parts = []
        
        # Tool call streaming accumulator
        # Map of index -> {id, name, arguments_str}
        acc_tool_calls: dict[int, dict[str, Any]] = {}

        in_thinking_tags = False

        with httpx.Client(timeout=60.0) as client:
            with client.stream("POST", endpoint, headers=headers, json=payload) as response:
                if response.status_code >= 400:
                    raise LLMError(f"HTTP {response.status_code}: {response.read().decode('utf-8')}")

                for line in response.iter_lines():
                    if not line.strip():
                        continue
                    if line.startswith("data: "):
                        data_str = line[6:].strip()
                        if data_str == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data_str)
                        except Exception:
                            continue

                        choices = chunk.get("choices", [])
                        if not choices:
                            continue

                        delta = choices[0].get("delta", {})

                        # 1. Check for explicit reasoning/thinking field (e.g. DeepSeek reasoning_content)
                        r_content = delta.get("reasoning_content") or delta.get("reasoning")
                        if r_content:
                            thinking_parts.append(r_content)
                            if on_thinking_chunk:
                                on_thinking_chunk(r_content)
                            continue

                        # 2. Check for standard text content
                        text = delta.get("content") or ""
                        if text:
                            # Parse tags inline
                            # Simple tag tracker: if we see <think>, switch to thinking mode
                            # If we see </think>, switch back to content mode
                            if "<think>" in text:
                                in_thinking_tags = True
                                parts = text.split("<think>")
                                if parts[0] and not in_thinking_tags:
                                    content_parts.append(parts[0])
                                    if on_content_chunk:
                                        on_content_chunk(parts[0])
                                text = parts[1] if len(parts) > 1 else ""

                            if "</think>" in text:
                                in_thinking_tags = False
                                parts = text.split("</think>")
                                if parts[0]:
                                    thinking_parts.append(parts[0])
                                    if on_thinking_chunk:
                                        on_thinking_chunk(parts[0])
                                text = parts[1] if len(parts) > 1 else ""

                            if text:
                                if in_thinking_tags:
                                    thinking_parts.append(text)
                                    if on_thinking_chunk:
                                        on_thinking_chunk(text)
                                else:
                                    content_parts.append(text)
                                    if on_content_chunk:
                                        on_content_chunk(text)

                        # 3. Check for streaming tool calls
                        t_calls = delta.get("tool_calls", [])
                        for tc in t_calls:
                            idx = tc.get("index", 0)
                            if idx not in acc_tool_calls:
                                acc_tool_calls[idx] = {"id": "", "name": "", "arguments_str": ""}
                            
                            if "id" in tc:
                                acc_tool_calls[idx]["id"] = tc["id"]
                            
                            fn = tc.get("function", {})
                            if "name" in fn:
                                acc_tool_calls[idx]["name"] = fn["name"]
                            if "arguments" in fn:
                                acc_tool_calls[idx]["arguments_str"] += fn["arguments"]

        # Reconstruct tool calls
        tool_calls = []
        for idx in sorted(acc_tool_calls.keys()):
            tc_data = acc_tool_calls[idx]
            try:
                args = json.loads(tc_data["arguments_str"]) if tc_data["arguments_str"] else {}
            except Exception:
                args = {}
            tool_calls.append(ToolCall(
                call_id=tc_data["id"],
                name=tc_data["name"],
                arguments=args
            ))

        final_content = "".join(content_parts).strip()
        final_thinking = "".join(thinking_parts).strip() if thinking_parts else None

        return LLMResponse(
            content=final_content,
            thinking=final_thinking,
            tool_calls=tool_calls
        )
