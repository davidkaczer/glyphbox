"""
LLM client for the NetHack agent.

Supports the OpenAI API (default), OpenRouter, and direct Anthropic API.
"""

import json
import logging
import os
from dataclasses import dataclass
from typing import Any, Optional

from openai import AsyncOpenAI, BadRequestError

from src.tui.logging import LLMLogger

logger = logging.getLogger(__name__)
llm_logger = LLMLogger()

# Default API base URL per provider (used when no base_url is given)
PROVIDER_BASE_URLS = {
    "openai": "https://api.openai.com/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "anthropic": "https://api.anthropic.com/v1/",
}

# Environment variables checked (in order) for each provider's API key
PROVIDER_API_KEY_ENV = {
    "openai": ("OPENAI_API_KEY",),
    "openrouter": ("OPENROUTER_API_KEY", "OPENROUTER_KEY"),
    "anthropic": ("ANTHROPIC_API_KEY",),
}


# Base tool - always available
EXECUTE_CODE_TOOL = {
    "type": "function",
    "function": {
        "name": "execute_code",
        "description": "Run Python code that interacts with the game. Use for ad-hoc commands like moving, fighting, picking up items. Batch multiple operations together.",
        "parameters": {
            "type": "object",
            "properties": {
                "reasoning": {
                    "type": "string",
                    "description": "1-2 sentence explanation of what the code will do. Be concise - do NOT repeat map analysis or game state here."
                },
                "code": {
                    "type": "string",
                    "description": "Python code to execute. Has access to 'nh' (game API) and Direction enum. All calls are synchronous - do NOT use await. Do NOT include lengthy comments repeating your reasoning - the code should be clean and minimal."
                }
            },
            "required": ["reasoning", "code"]
        }
    }
}

# View full map tool - only when local_map_mode is enabled
VIEW_FULL_MAP_TOOL = {
    "type": "function",
    "function": {
        "name": "view_full_map",
        "description": "View the ENTIRE dungeon level map (all 21 rows). Use ONLY when the local view is insufficient - e.g. to plan exploration routes, remember distant item locations, or understand overall level layout. Do NOT use every turn - it's expensive. The local view shown each turn is enough for tactical decisions.",
        "parameters": {
            "type": "object",
            "properties": {
                "reasoning": {
                    "type": "string",
                    "description": "Why you need the full map view right now"
                }
            },
            "required": ["reasoning"]
        }
    }
}

# Core tools (for backward compatibility)
CORE_TOOLS = [EXECUTE_CODE_TOOL, VIEW_FULL_MAP_TOOL]

# Skill tool definitions (only when skills_enabled=True)
SKILL_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "write_skill",
            "description": "Save reusable code as a named skill for later use. Use when you find yourself repeating patterns.",
            "parameters": {
                "type": "object",
                "properties": {
                    "reasoning": {
                        "type": "string",
                        "description": "Brief explanation of what this skill does"
                    },
                    "skill_name": {
                        "type": "string",
                        "description": "Name for the skill (snake_case)"
                    },
                    "code": {
                        "type": "string",
                        "description": "Python code for the skill. MUST be an async function: async def skill_name(nh, **params):"
                    }
                },
                "required": ["reasoning", "skill_name", "code"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "invoke_skill",
            "description": "Run a previously saved skill.",
            "parameters": {
                "type": "object",
                "properties": {
                    "reasoning": {
                        "type": "string",
                        "description": "Brief explanation of why you're invoking this skill"
                    },
                    "skill_name": {
                        "type": "string",
                        "description": "Name of the skill to invoke"
                    },
                    "params": {
                        "type": "object",
                        "description": "Parameters to pass to the skill"
                    }
                },
                "required": ["reasoning", "skill_name"]
            }
        }
    }
]

# All tools combined (for backward compatibility)
AGENT_TOOLS = CORE_TOOLS + SKILL_TOOLS


def get_agent_tools(skills_enabled: bool = False, local_map_mode: bool = False) -> list[dict]:
    """Get the list of tools based on configuration.

    Args:
        skills_enabled: Whether skill tools (write_skill, invoke_skill) are enabled
        local_map_mode: Whether agent sees local map (True) or full map (False).
                        view_full_map tool is only included when local_map_mode=True.

    Returns:
        List of tool definitions for the LLM
    """
    tools = [EXECUTE_CODE_TOOL]

    # Only include view_full_map when agent sees local map (needs way to see full)
    if local_map_mode:
        tools.append(VIEW_FULL_MAP_TOOL)

    if skills_enabled:
        tools.extend(SKILL_TOOLS)

    return tools


@dataclass
class ToolCall:
    """A tool call from the LLM."""

    name: str
    arguments: dict


@dataclass
class LLMResponse:
    """Response from the LLM."""

    content: str
    model: str
    usage: Optional[dict] = None
    finish_reason: Optional[str] = None
    tool_call: Optional[ToolCall] = None  # Tool call if model invoked a tool
    # Extended thinking / reasoning support (OpenRouter)
    reasoning: Optional[str] = None  # The model's thinking/reasoning text
    reasoning_details: Optional[list] = None  # Full reasoning blocks for re-feeding


class LLMClient:
    """
    Client for interacting with LLMs via OpenAI, OpenRouter or Anthropic.

    Uses the OpenAI Responses API for provider "openai", and the OpenAI-compatible
    Chat Completions API for everything else.
    """

    def __init__(
        self,
        provider: str = "openai",
        model: str = "gpt-5.2",
        base_url: Optional[str] = None,
        temperature: float = 0.2,
        api_key: Optional[str] = None,
        reasoning: Optional[str] = None,
        openai_api: str = "responses",
    ):
        """
        Initialize the LLM client.

        Args:
            provider: LLM provider ("openai", "openrouter" or "anthropic")
            model: Model identifier
            base_url: API base URL (defaults to the provider's standard endpoint)
            temperature: Sampling temperature
            api_key: API key (defaults to the provider's env var, e.g. OPENAI_API_KEY)
            reasoning: Reasoning effort level ("none", "minimal", "low", "medium", "high", "xhigh")
                      or None to disable. Sent as OpenAI's reasoning.effort (Responses API),
                      reasoning_effort (Chat Completions) or OpenRouter's reasoning.effort.
            openai_api: For provider "openai": "responses" (default, required by newer
                      models for tools + reasoning) or "chat" (Chat Completions, for
                      OpenAI-compatible servers without /v1/responses).
        """
        if openai_api not in ("responses", "chat"):
            raise ValueError(f"Unknown openai_api '{openai_api}'. Expected 'responses' or 'chat'")
        if provider not in PROVIDER_BASE_URLS:
            raise ValueError(
                f"Unknown provider '{provider}'. Expected one of: {', '.join(PROVIDER_BASE_URLS)}"
            )
        self.provider = provider
        self.model = model
        self.temperature = temperature
        # Store reasoning effort (None or "none" means disabled)
        self.reasoning_effort = None
        if reasoning and reasoning.lower() != "none":
            self.reasoning_effort = reasoning.lower()

        self.use_responses_api = provider == "openai" and openai_api == "responses"

        # Optional params the model has rejected (e.g. "temperature"), omitted from later requests
        self._dropped_params: set[str] = set()

        # Get API key from env if not provided
        env_vars = PROVIDER_API_KEY_ENV[provider]
        if api_key is None:
            api_key = next((os.environ[v] for v in env_vars if os.environ.get(v)), None)

        if not api_key:
            raise ValueError(f"No API key found. Set {' or '.join(env_vars)} environment variable.")

        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url or PROVIDER_BASE_URLS[provider],
        )

        reasoning_info = f", reasoning={self.reasoning_effort}" if self.reasoning_effort else ""
        api_info = ", api=responses" if self.use_responses_api else ""
        logger.info(f"LLMClient initialized: provider={provider}, model={model}{reasoning_info}{api_info}")

    def _chat_kwargs(
        self,
        messages: list[dict],
        temperature: Optional[float],
        max_tokens: Optional[int],
        tools: Optional[list[dict]],
        tool_choice: Optional[str],
    ) -> dict[str, Any]:
        """Build Chat Completions kwargs (OpenRouter, Anthropic, OpenAI with openai_api="chat")."""
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature if temperature is not None else self.temperature,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = tool_choice

        if self.provider == "openai":
            # OpenAI reasoning models reject custom temperatures and max_tokens
            if self.reasoning_effort:
                del kwargs["temperature"]
            if max_tokens is not None:
                kwargs["max_completion_tokens"] = max_tokens
            if self.reasoning_effort:
                kwargs["reasoning_effort"] = self.reasoning_effort
        else:
            if max_tokens is not None:
                kwargs["max_tokens"] = max_tokens
            if self.reasoning_effort:
                kwargs["extra_body"] = {"reasoning": {"effort": self.reasoning_effort}}

        return kwargs

    def _responses_kwargs(
        self,
        messages: list[dict],
        temperature: Optional[float],
        max_tokens: Optional[int],
        tools: Optional[list[dict]],
        tool_choice: Optional[str],
    ) -> dict[str, Any]:
        """Build OpenAI Responses API kwargs from chat-style messages and tools."""
        # System messages become instructions; extra keys (e.g. OpenRouter
        # reasoning_details) aren't accepted by the Responses API
        instructions = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
        input_items = [
            {"role": m["role"], "content": m["content"]}
            for m in messages
            if m["role"] != "system"
        ]

        kwargs: dict[str, Any] = {
            "model": self.model,
            "input": input_items,
            # Full history is sent every request, so nothing needs storing server-side
            "store": False,
        }
        if instructions:
            kwargs["instructions"] = instructions
        if tools:
            # Chat format nests the definition under "function"; Responses is flat
            kwargs["tools"] = [
                {
                    "type": "function",
                    "name": t["function"]["name"],
                    "description": t["function"].get("description", ""),
                    "parameters": t["function"]["parameters"],
                    "strict": False,
                }
                for t in tools
            ]
            kwargs["tool_choice"] = tool_choice
        if max_tokens is not None:
            kwargs["max_output_tokens"] = max_tokens
        if self.reasoning_effort:
            # Summaries are shown as the model's reasoning text
            kwargs["reasoning"] = {"effort": self.reasoning_effort, "summary": "auto"}
        else:
            kwargs["temperature"] = temperature if temperature is not None else self.temperature

        return kwargs

    @staticmethod
    def _drop_param(kwargs: dict[str, Any], param: str) -> Optional[dict[str, Any]]:
        """Return kwargs without an optional param, or None if it isn't present."""
        if param == "temperature" and "temperature" in kwargs:
            return {k: v for k, v in kwargs.items() if k != "temperature"}
        if param == "reasoning.summary" and "summary" in kwargs.get("reasoning", {}):
            reasoning = {k: v for k, v in kwargs["reasoning"].items() if k != "summary"}
            return {**kwargs, "reasoning": reasoning}
        return None

    async def _call(self, create, kwargs: dict[str, Any]):
        """
        Call the API, retrying without optional params the model rejects.

        Some models refuse a custom temperature or reasoning summaries (e.g.
        unverified organizations). Rejected params are remembered and left out
        of later requests.
        """
        for param in self._dropped_params:
            kwargs = self._drop_param(kwargs, param) or kwargs

        while True:
            try:
                return await create(**kwargs)
            except BadRequestError as e:
                error_text = f"{e.param or ''} {e}"
                retry_kwargs = None
                for param in ("temperature", "reasoning.summary"):
                    if param.split(".")[-1] in error_text:
                        retry_kwargs = self._drop_param(kwargs, param)
                        if retry_kwargs is not None:
                            break
                if retry_kwargs is None:
                    llm_logger.log_error(str(e), {"model": self.model})
                    raise
                logger.warning(f"Model {self.model} rejected '{param}', retrying without it")
                self._dropped_params.add(param)
                kwargs = retry_kwargs
            except Exception as e:
                llm_logger.log_error(str(e), {"model": self.model})
                raise

    async def _request(
        self,
        messages: list[dict],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        tools: Optional[list[dict]] = None,
        tool_choice: Optional[str] = None,
        log_request: bool = True,
    ) -> LLMResponse:
        """Send one request via the configured API and normalize the result."""
        if self.use_responses_api:
            kwargs = self._responses_kwargs(messages, temperature, max_tokens, tools, tool_choice)
        else:
            kwargs = self._chat_kwargs(messages, temperature, max_tokens, tools, tool_choice)

        if log_request:
            llm_logger.log_request(
                model=self.model,
                messages=messages,
                temperature=kwargs.get("temperature"),
                max_tokens=max_tokens,
            )

        if self.use_responses_api:
            response = await self._call(self.client.responses.create, kwargs)
            return self._parse_responses_result(response)
        response = await self._call(self.client.chat.completions.create, kwargs)
        return self._parse_chat_result(response)

    @staticmethod
    def _parse_tool_call(name: str, arguments: str) -> Optional[ToolCall]:
        try:
            return ToolCall(name=name, arguments=json.loads(arguments))
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse tool call arguments: {e}")
            return None

    def _parse_chat_result(self, response) -> LLMResponse:
        choice = response.choices[0]

        tool_call = None
        if choice.message.tool_calls:
            tc = choice.message.tool_calls[0]
            tool_call = self._parse_tool_call(tc.function.name, tc.function.arguments)

        usage = None
        if response.usage:
            usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            }

        return LLMResponse(
            content=choice.message.content or "",
            model=response.model,
            usage=usage,
            finish_reason=choice.finish_reason,
            tool_call=tool_call,
            # Reasoning/thinking tokens are extra attributes on the message (OpenRouter)
            reasoning=getattr(choice.message, "reasoning", None),
            reasoning_details=getattr(choice.message, "reasoning_details", None),
        )

    def _parse_responses_result(self, response) -> LLMResponse:
        tool_call = None
        summaries = []
        for item in response.output:
            if item.type == "function_call" and tool_call is None:
                tool_call = self._parse_tool_call(item.name, item.arguments)
            elif item.type == "reasoning":
                summaries.extend(s.text for s in item.summary or [])

        usage = None
        if response.usage:
            usage = {
                "prompt_tokens": response.usage.input_tokens,
                "completion_tokens": response.usage.output_tokens,
                "total_tokens": response.usage.total_tokens,
            }

        finish_reason = response.status
        if response.incomplete_details and response.incomplete_details.reason:
            finish_reason = response.incomplete_details.reason

        return LLMResponse(
            content=response.output_text or "",
            model=response.model,
            usage=usage,
            finish_reason=finish_reason,
            tool_call=tool_call,
            reasoning="\n\n".join(summaries) or None,
        )

    def _log_response(self, response: LLMResponse, suffix: str = "") -> None:
        llm_logger.log_response(
            content=response.content + suffix,
            model=response.model,
            usage=response.usage,
            finish_reason=response.finish_reason,
        )

    async def complete(
        self,
        prompt: str,
        system: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> LLMResponse:
        """
        Generate a completion from the LLM.

        Args:
            prompt: The user prompt
            system: Optional system message
            temperature: Override default temperature
            max_tokens: Maximum tokens to generate (None for no limit)

        Returns:
            LLMResponse with the generated content
        """
        return await self.complete_with_history(
            [{"role": "user", "content": prompt}],
            system=system,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    async def complete_with_history(
        self,
        messages: list[dict],
        system: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> LLMResponse:
        """
        Generate a completion with conversation history.

        Args:
            messages: List of {"role": "user"|"assistant", "content": "..."}
            system: Optional system message
            temperature: Override default temperature
            max_tokens: Maximum tokens to generate

        Returns:
            LLMResponse with the generated content
        """
        full_messages = []
        if system:
            full_messages.append({"role": "system", "content": system})
        full_messages.extend(messages)

        response = await self._request(full_messages, temperature, max_tokens)
        self._log_response(response)
        return response

    async def complete_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        system: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        max_tool_retries: int = 5,
    ) -> LLMResponse:
        """
        Generate a completion with tool calling.

        Args:
            messages: List of {"role": "user"|"assistant", "content": "..."}
            tools: List of tool definitions (use AGENT_TOOLS for agent actions)
            system: Optional system message
            temperature: Override default temperature
            max_tokens: Maximum tokens to generate
            max_tool_retries: Max attempts to get a tool call (default 5)

        Returns:
            LLMResponse with tool_call populated if model invoked a tool
        """
        full_messages = []

        if system:
            full_messages.append({"role": "system", "content": system})

        full_messages.extend(messages)

        # Use "required" for models that support it (forces tool use, no text-only responses)
        # Fall back to "auto" for models that don't support it (GLM, some others)
        model_lower = self.model.lower()
        if self.provider == "openai" or "claude" in model_lower or "anthropic" in model_lower:
            tool_choice = "required"
        else:
            tool_choice = "auto"

        # Retry loop to ensure we get a tool call
        for attempt in range(max_tool_retries):
            response = await self._request(
                full_messages,
                temperature,
                max_tokens,
                tools=tools,
                tool_choice=tool_choice,
                log_request=attempt == 0,  # Log full request only on first attempt
            )

            # If we got a tool call, log and return
            if response.tool_call:
                reasoning_info = f" [reasoning: {len(response.reasoning)} chars]" if response.reasoning else ""
                self._log_response(response, f" [tool: {response.tool_call.name}]{reasoning_info}")
                return response

            # No tool call - log and retry
            content = response.content
            logger.warning(
                f"Model did not call a tool (attempt {attempt + 1}/{max_tool_retries}). "
                f"Response: {content[:200]}{'...' if len(content) > 200 else ''}"
            )

            # Add the assistant's response and a nudge to use tools
            # Include reasoning_details if present to preserve thinking context
            assistant_msg: dict[str, Any] = {"role": "assistant", "content": content}
            if response.reasoning_details:
                assistant_msg["reasoning_details"] = response.reasoning_details
            full_messages.append(assistant_msg)
            full_messages.append({
                "role": "user",
                "content": "You must use the execute_code tool to take an action. Please call the tool now."
            })

        # Exhausted retries - return last response without tool call
        logger.error(f"Failed to get tool call after {max_tool_retries} attempts")
        self._log_response(response, " [NO TOOL CALL]")
        return response


def create_client_from_config(config) -> LLMClient:
    """Create an LLM client from configuration."""
    return LLMClient(
        provider=config.agent.provider,
        model=config.agent.model,
        base_url=config.agent.base_url,
        temperature=config.agent.temperature,
        reasoning=config.agent.reasoning,
        openai_api=config.agent.openai_api,
    )
