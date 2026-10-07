import json
import os
from typing import Any

from openai import OpenAI

from pawplan.agent.dev_fallback import run_dev_fallback
from pawplan.agent.logutil import log_event
from pawplan.agent.prompts import SYSTEM_PROMPT
from pawplan.agent.tools_schema import TOOLS
from pawplan.tools.search_knowledge import search_knowledge
from pawplan.tools.search_parks import search_parks
from pawplan.tools.search_restaurants import search_restaurants


def _dispatch_tool(name: str, arguments: dict[str, Any]) -> dict:
    if name == "search_knowledge":
        return search_knowledge(**arguments)
    if name == "search_parks":
        return search_parks(**arguments)
    if name == "search_restaurants":
        return search_restaurants(**arguments)
    return {"error": "unknown_tool", "name": name}


def run_agent(user_question: str) -> dict:
    """
    Returns {"reply": str, "mode": "deepseek"|"dev", "tool_trace": list}.
    """
    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        reply, trace = run_dev_fallback(user_question)
        log_event(
            {
                "mode": "dev",
                "user": user_question,
                "tool_trace": trace,
                "reply_preview": reply[:240],
            }
        )
        return {"reply": reply, "mode": "dev", "tool_trace": trace}

    max_steps = int(os.environ.get("MAX_TOOL_STEPS", "4"))
    client = OpenAI(
        api_key=api_key,
        base_url=os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
    )
    model = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_question},
    ]
    tool_trace: list[dict] = []

    for _ in range(max_steps):
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=TOOLS,
        )
        message = response.choices[0].message

        if not message.tool_calls:
            reply = message.content or ""
            log_event(
                {
                    "mode": "deepseek",
                    "user": user_question,
                    "tool_trace": tool_trace,
                    "reply_preview": reply[:240],
                }
            )
            return {
                "reply": reply,
                "mode": "deepseek",
                "tool_trace": tool_trace,
            }

        messages.append(message.model_dump(exclude_none=True))

        for call in message.tool_calls:
            args = json.loads(call.function.arguments)
            result = _dispatch_tool(call.function.name, args)
            tool_trace.append(
                {
                    "tool": call.function.name,
                    "arguments": args,
                    "result_count": result.get("count"),
                }
            )
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": json.dumps(result, ensure_ascii=False, default=str),
                }
            )

    reply = "在工具调用次数上限内未能完成请求，请简化问题后重试。"
    log_event(
        {
            "mode": "deepseek",
            "user": user_question,
            "tool_trace": tool_trace,
            "reply_preview": reply,
            "error": "tool_step_limit",
        }
    )
    return {
        "reply": reply,
        "mode": "deepseek",
        "tool_trace": tool_trace,
    }
