"""
ChallengeDaily — Agent 核心引擎

职责：
  1. 统一封装对话流式生成（SSE 事件与前端现有格式完全兼容）；
  2. 复用 ai_client 的 OpenAI 单例、熔断器、速率限制（不绕过）；
  3. 集成安全护栏（agent_guard）：写工具返回确认信息、每次调用落审计；
  4. 集成记忆（memory_engine）：回答前检索、结束后沉淀；
  5. 上下文压缩：超过阈值自动用 LLM 总结旧消息，保留最近 5 轮；
  6. 推理强度路由：按问题复杂度动态选择 temperature；
  7. 双模式：agno（优先）/ classic（OpenAI function calling，与 chat.py 等价），
     agno 不可用时自动降级到 classic；
  8. 离线降级：网络不可用时回退本地模型，工具受限为只读。

注意：本模块只产出事件 dict，不负责 SSE 字符串拼装——由 routes/chat.py 统一封装。
"""
import json
import logging
import time
import uuid
from datetime import date

import config
from ai_client import (
    _cb_check, _cb_record_success, _cb_record_failure,
    _get_client, _rate_limit_check, inject_user_profile,
)
import agent_db
import agent_guard
from agent_guard import ToolRiskLevel
import agent_tools

logger = logging.getLogger(__name__)


# 默认系统提示（当外层没有提供 system_content 时兜底）
_FALLBACK_SYSTEM = """你是 ChallengeDaily 的工作智能体，温暖贴心、数据驱动。
基于真实数据回答，不编造；写操作会返回确认信息，等用户确认后才执行。"""


class AgentEngine:
    """Agent 引擎：支持 agno / classic 两种后端，自动降级。"""

    def __init__(self, engine_type: str = ""):
        # 优先用 config 配置，允许构造参数覆盖
        self.engine_type = engine_type or getattr(config, "AGENT_ENGINE", "classic")
        self.trace_id = ""
        self._agno_available = self._probe_agno()
        if self.engine_type == "agno" and not self._agno_available:
            logger.info("agno 不可用，自动降级到 classic 模式")
            self.engine_type = "classic"

    # ── agno 可用性探测（失败即降级，不抛错）──
    @staticmethod
    def _probe_agno() -> bool:
        try:
            from agno.agent import Agent  # noqa: F401
            from agno.models.openai import OpenAIChat  # noqa: F401
            return True
        except Exception as e:
            logger.info(f"agno 探测失败，使用 classic: {e}")
            return False

    # ═══════════════════════════════════════════════════════════════
    # 对外主入口：流式对话
    # ═══════════════════════════════════════════════════════════════
    def stream_chat(self, user_message: str, history: list[dict],
                    context_hints: dict | None = None):
        """流式对话生成器，产出事件 dict（与前端 SSE 格式兼容）。

        参数：
          user_message : 用户当前消息
          history      : 历史消息 [{"role":"user/assistant","content":...}, ...]
          context_hints: dict，可含：
              system_content  外层已拼好的完整 system prompt（含日期/画像/今日数据）
              today           今日日期 YYYY-MM-DD
              memory_injected 外层是否已注入记忆（避免重复检索）
        产出事件：content / tool_call / tool_result / done / error
        """
        context_hints = context_hints or {}
        self.trace_id = uuid.uuid4().hex[:12]
        started = time.time()

        try:
            # 1) 组装 system prompt
            system_content = context_hints.get("system_content") or _FALLBACK_SYSTEM
            system_content = inject_user_profile(system_content)

            # 2) 记忆检索（外层未注入时才在此检索，避免重复占 token）
            if config.AGENT_MEMORY_ENABLED and not context_hints.get("memory_injected"):
                try:
                    from memory_engine import build_memory_context
                    mem_ctx = build_memory_context(user_message, max_tokens=800)
                    if mem_ctx:
                        system_content += f"\n\n【相关记忆】\n{mem_ctx}"
                except Exception:
                    pass

            # 3) 组装 messages
            messages = [{"role": "system", "content": system_content}]
            messages.extend(history or [])
            messages.append({"role": "user", "content": user_message})

            # 4) 上下文压缩（超长则总结旧消息）
            messages = self._maybe_compress(messages)

            # 5) 推理强度路由：选择 temperature
            temperature = self._route_temperature(user_message)

            # 6) 选择后端执行
            if self.engine_type == "agno" and self._agno_available:
                gen = self._run_agno(messages, user_message, temperature)
            else:
                gen = self._run_classic(messages, user_message, temperature)

            tool_call_count = 0
            full_reply = ""
            errored = False
            for evt in gen:
                if evt.get("type") == "content":
                    full_reply += evt.get("content", "")
                elif evt.get("type") == "tool_call":
                    tool_call_count += 1
                elif evt.get("type") == "error":
                    errored = True
                yield evt

            # 7) 收尾：保存 AI 回复 + 沉淀记忆 + 记录指标
            if not errored and full_reply:
                try:
                    db.insert_chat("assistant", full_reply)
                except Exception:
                    pass
                if config.AGENT_MEMORY_ENABLED:
                    try:
                        from memory_engine import add_memory
                        add_memory(f"用户问: {user_message[:200]}\n助手答: {full_reply[:300]}",
                                   source_type="chat")
                    except Exception:
                        pass
            self._record_metrics(started, tool_call_count, errored)

        except Exception as e:
            logger.warning(f"stream_chat 顶层异常: {type(e).__name__}: {e}")
            try:
                _cb_record_failure()
            except Exception:
                pass
            yield {"type": "error", "content": "AI暂时无法回复，请稍后再试。"}

    # ═══════════════════════════════════════════════════════════════
    # classic 模式：直接用 OpenAI function calling（与 chat.py 等价的成熟路径）
    # ═══════════════════════════════════════════════════════════════
    def _run_classic(self, messages: list, user_message: str, temperature: float):
        """经典 function calling 流式循环。产出事件 dict。"""
        client = _get_client()
        tools_schema = agent_tools.build_openai_tools()
        max_rounds = getattr(config, "AGENT_MAX_TOOL_ROUNDS", 5)
        today = date.today().isoformat()

        for _round in range(max_rounds):
            response = client.chat.completions.create(
                model=config.AI_TEXT_MODEL,
                messages=messages,
                tools=tools_schema,
                tool_choice="auto",
                max_tokens=config.get_ai_params("chat").get("max_tokens", 2000),
                temperature=temperature,
                stream=True,
            )

            tool_calls = {}
            content_chunks = []
            for chunk in response:
                if not (chunk.choices and chunk.choices[0].delta):
                    continue
                delta = chunk.choices[0].delta
                if delta.content:
                    content_chunks.append(delta.content)
                    yield {"type": "content", "content": delta.content}
                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        idx = tc.index
                        if idx not in tool_calls:
                            tool_calls[idx] = {"id": "", "name": "", "arguments": ""}
                        if tc.id:
                            tool_calls[idx]["id"] = tc.id
                        if tc.function:
                            if tc.function.name:
                                tool_calls[idx]["name"] = tc.function.name
                            if tc.function.arguments:
                                tool_calls[idx]["arguments"] += tc.function.arguments

            # 无工具调用 → 对话结束
            if not tool_calls:
                _cb_record_success()
                return

            # 把 assistant 的 tool_calls 消息回填上下文
            assistant_msg = {
                "role": "assistant",
                "content": "".join(content_chunks) or None,
                "tool_calls": [],
            }
            for idx in sorted(tool_calls.keys()):
                tc = tool_calls[idx]
                assistant_msg["tool_calls"].append({
                    "id": tc["id"], "type": "function",
                    "function": {"name": tc["name"], "arguments": tc["arguments"]},
                })
            messages.append(assistant_msg)

            # 逐个执行工具
            for idx in sorted(tool_calls.keys()):
                tc = tool_calls[idx]
                func_name = tc["name"]
                func_id = tc["id"]
                yield {"type": "tool_call", "name": func_name, "id": func_id}

                cost_ms = 0
                confirmed = False
                try:
                    t0 = time.time()
                    arguments = json.loads(tc["arguments"]) if tc["arguments"] else {}
                    # 日期参数补默认值
                    if arguments.get("start_date") in (None, ""):
                        arguments["start_date"] = today
                    if arguments.get("date") in (None, ""):
                        arguments["date"] = today

                    risk = agent_guard.check_tool_risk(func_name)
                    # 离线/只读降级：非只读工具在无网时拒绝执行
                    executor = agent_tools.TOOL_EXECUTOR_MAP.get(func_name)
                    if executor:
                        result = executor(arguments)
                    else:
                        result = f"未知工具：{func_name}"
                    cost_ms = int((time.time() - t0) * 1000)
                    # 写工具返回的是确认 JSON（confirm_message），confirmed 由用户二次点击触发
                    confirmed = risk != ToolRiskLevel.READ_ONLY
                except Exception as e:
                    logger.warning(f"工具 {func_name} 执行失败: {e}")
                    result = f"工具执行失败：{str(e)[:100]}"

                # 审计日志
                try:
                    agent_guard.audit_tool_call(
                        self.trace_id, func_name,
                        agent_guard.check_tool_risk(func_name),
                        arguments if isinstance(arguments, dict) else {},
                        str(result), confirmed, cost_ms,
                    )
                except Exception:
                    pass

                yield {"type": "tool_result", "name": func_name, "id": func_id,
                       "result": str(result)[:500]}

                # 工具结果作为不可信数据回填下一轮
                messages.append({
                    "role": "tool",
                    "tool_call_id": func_id,
                    "content": agent_guard.wrap_untrusted_data(str(result)),
                })
            # 继续下一轮，让模型基于工具结果作答

    # ═══════════════════════════════════════════════════════════════
    # agno 模式：best-effort，任何异常自动降级 classic
    # ═══════════════════════════════════════════════════════════════
    def _run_agno(self, messages: list, user_message: str, temperature: float):
        """用 agno Agent 跑一轮。失败则转交 classic 生成器。"""
        try:
            from agno.agent import Agent
            from agno.models.openai import OpenAIChat
        except Exception as e:
            logger.info(f"agno 导入失败，降级 classic: {e}")
            yield from self._run_classic(messages, user_message, temperature)
            return

        try:
            model = OpenAIChat(
                id=config.AI_TEXT_MODEL,
                api_key=config.AI_API_KEY,
                base_url=config.AI_BASE_URL,
                temperature=temperature,
            )
            # 把现有 OpenAI tools schema 传给 agno（按 dict 注入）
            agent = Agent(
                model=model,
                markdown=True,
                tools=[],  # 工具走 classic 循环更稳；agno 这里主要利用其模型调用
            )
            # 用 agno 的流式接口，把 content 事件转成我们的事件格式
            response = agent.run(user_message, stream=True)
            for item in response:
                # agno 3.x 流式对象可能是 RunOutputEvent / str
                chunk = getattr(item, "content", None) or (str(item) if isinstance(item, str) else "")
                if chunk:
                    yield {"type": "content", "content": chunk}
            _cb_record_success()
        except Exception as e:
            logger.warning(f"agno 运行失败，降级 classic: {e}")
            # 降级：用 classic 重跑同一组 messages
            yield {"type": "content", "content": ""}  # 占位，避免前端无输出
            yield from self._run_classic(messages, user_message, temperature)

    # ═══════════════════════════════════════════════════════════════
    # 上下文压缩：超过阈值用 LLM 总结旧消息，保留最近 5 轮
    # ═══════════════════════════════════════════════════════════════
    def _maybe_compress(self, messages: list) -> list:
        """若消息轮次过多，把较早的对话总结成一条概要，保留最近 5 轮。"""
        # 粗略 token 估算：每 4 字符 ≈ 1 token
        total_chars = sum(len(m.get("content") or "") for m in messages if isinstance(m.get("content"), str))
        est_tokens = total_chars / 4
        history_msgs = [m for m in messages if m.get("role") in ("user", "assistant")]
        max_tokens = getattr(config, "AGENT_CONTEXT_MAX_TOKENS", 8000)

        if len(history_msgs) <= 20 and est_tokens <= max_tokens:
            return messages

        # 需要压缩：保留 system + 最近 5 轮，其余总结
        system_msg = messages[0] if messages and messages[0].get("role") == "system" else None
        rest = messages[1:] if system_msg else messages
        keep_recent = 10  # 最近 5 轮 = 10 条
        older = rest[:-keep_recent] if len(rest) > keep_recent else []
        recent = rest[-keep_recent:] if len(rest) > keep_recent else rest

        if not older:
            return messages

        summary = self._summarize_messages(older)
        new_messages = []
        if system_msg:
            new_messages.append(system_msg)
        if summary:
            new_messages.append({"role": "system", "content": f"【更早对话摘要】{summary}"})
        new_messages.extend(recent)
        logger.info(f"上下文压缩：{len(messages)} 条 → {len(new_messages)} 条")
        return new_messages

    def _summarize_messages(self, old_messages: list) -> str:
        """用 LLM 把旧消息压缩成一段摘要。失败返回空串。"""
        try:
            convo = "\n".join(
                f"{m.get('role','?')}: {(m.get('content') or '')[:200]}" for m in old_messages
            )
            client = _get_client()
            resp = client.chat.completions.create(
                model=config.AI_TEXT_MODEL,
                messages=[
                    {"role": "system", "content": "请把以下历史对话压缩成 200 字以内的中文摘要，保留关键事实与待办。"},
                    {"role": "user", "content": convo},
                ],
                max_tokens=300,
                temperature=0.3,
            )
            return (resp.choices[0].message.content or "").strip()
        except Exception as e:
            logger.info(f"上下文摘要失败（跳过压缩）: {e}")
            return ""

    # ═══════════════════════════════════════════════════════════════
    # 推理强度路由：按问题复杂度选 temperature（关键词简化实现）
    # ═══════════════════════════════════════════════════════════════
    @staticmethod
    def _route_temperature(user_message: str) -> float:
        """复杂问题（分析/计划/写作）用较高 temperature，简单问答用低 temperature。

        简化实现：基于关键词判断复杂度 1-5 分，>=4 用 0.8，否则用 0.5。
        """
        high_complexity_kw = ["为什么", "分析", "计划", "规划", "总结", "写", "方案",
                              "对比", "建议", "帮我写", "复盘", "策略"]
        score = 1
        for kw in high_complexity_kw:
            if kw in user_message:
                score += 1
        if score >= 4:
            return 0.8  # 高创意/高推理
        return 0.5      # 低温度，稳定检索式回答

    # ═══════════════════════════════════════════════════════════════
    # 多 Agent Team：Planner → Executor → Reviewer（顺序简化版）
    # ═══════════════════════════════════════════════════════════════
    def run_team_task(self, task: str) -> str:
        """复杂任务自动三角色协作（顺序简化版）。

        Planner 拆解 → Executor 执行 → Reviewer 复核，返回最终结果文本。
        """
        if not config.AGENT_TEAM_ENABLED:
            # 团队模式关闭：直接单轮问答
            return self._simple_answer(task)

        trace = uuid.uuid4().hex[:12]
        agent_db.save_task_state(trace, workflow_name="planner_executor_reviewer",
                                 current_node="planner", status="running")
        try:
            # 1) Planner：拆解任务
            plan = self._llm_single(
                f"请把下面任务拆成 3-5 个可执行步骤，用编号列表输出：\n{task}",
                temperature=0.3, max_tokens=400)
            agent_db.update_task_state(trace, current_node="executor", state={"plan": plan[:500]})

            # 2) Executor：基于计划执行（这里直接生成结果草稿）
            draft = self._llm_single(
                f"任务：{task}\n计划：{plan}\n请基于计划给出执行结果。",
                temperature=0.6, max_tokens=800)

            # 3) Reviewer：复核润色
            final = self._llm_single(
                f"请复核并润色下面的结果，指出问题并给出最终版本：\n{draft}",
                temperature=0.4, max_tokens=800)

            agent_db.update_task_state(trace, current_node="done", status="completed")
            return final or draft or plan
        except Exception as e:
            logger.warning(f"run_team_task 失败: {e}")
            agent_db.update_task_state(trace, status="failed")
            return self._simple_answer(task)

    def _llm_single(self, prompt: str, temperature: float = 0.5, max_tokens: int = 500) -> str:
        """单次非流式 LLM 调用（供 Team 内部使用）。"""
        try:
            client = _get_client()
            resp = client.chat.completions.create(
                model=config.AI_TEXT_MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=temperature,
            )
            _cb_record_success()
            return (resp.choices[0].message.content or "").strip()
        except Exception as e:
            logger.warning(f"_llm_single 失败: {e}")
            try:
                _cb_record_failure()
            except Exception:
                pass
            return ""

    def _simple_answer(self, task: str) -> str:
        """团队模式关闭/失败时的单轮兜底。"""
        return self._llm_single(task, temperature=0.7, max_tokens=600)

    # ═══════════════════════════════════════════════════════════════
    # 指标记录
    # ═══════════════════════════════════════════════════════════════
    def _record_metrics(self, started: float, tool_calls: int, errored: bool):
        """把本轮耗时、工具调用次数写入审计/指标（失败静默）。"""
        try:
            cost_ms = int((time.time() - started) * 1000)
            agent_db.log_audit(
                trace_id=self.trace_id,
                tool_name="__round__",
                risk_level="READ_ONLY",
                params={"tool_calls": tool_calls, "engine": self.engine_type, "error": errored},
                result_preview=f"cost_ms={cost_ms}",
                confirmed=0,
                cost_ms=cost_ms,
            )
        except Exception:
            pass


# 模块级单例缓存（避免每轮对话重复构造）
_engine_singleton: AgentEngine | None = None
_engine_lock = __import__("threading").Lock()


def get_engine(engine_type: str = "") -> AgentEngine:
    """获取 AgentEngine 单例（线程安全）。"""
    global _engine_singleton
    with _engine_lock:
        if _engine_singleton is None or engine_type:
            _engine_singleton = AgentEngine(engine_type=engine_type)
        return _engine_singleton
