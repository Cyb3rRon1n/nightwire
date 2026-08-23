from collections.abc import Awaitable, Callable
from typing import Annotated, Literal, Union

import ollama
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from narrator.tools import ApplyCharacterUpdate, EndCombat, RequestRoll, StartCombat, UpdateWorld


# Each variant pairs a Literal tag with the *real* argument model from
# narrator/tools.py (not a loose dict) - Ollama's structured-output format
# param is a real JSON schema it constrains generation against, so a bare
# `tool_args: dict` gives the model nothing to be constrained by beyond the
# tool's name. This is what actually stops a model from inventing a
# plausible-but-wrong shape (e.g. `{"scene": ..., "enemies": [...]}` for
# start_combat, which only ever takes `{"reason": str}`) - a richer system
# prompt alone can reduce that, but only schema-level constraint prevents it.
class _NoTool(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tool: Literal[None] = None


class _RequestRollCall(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tool: Literal["request_roll"]
    tool_args: RequestRoll


class _ApplyCharacterUpdateCall(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tool: Literal["apply_character_update"]
    tool_args: ApplyCharacterUpdate


class _UpdateWorldCall(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tool: Literal["update_world"]
    tool_args: UpdateWorld


class _StartCombatCall(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tool: Literal["start_combat"]
    tool_args: StartCombat


class _EndCombatCall(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tool: Literal["end_combat"]
    tool_args: EndCombat


ToolCall = Annotated[
    Union[_NoTool, _RequestRollCall, _ApplyCharacterUpdateCall, _UpdateWorldCall, _StartCombatCall, _EndCombatCall],
    Field(discriminator="tool"),
]


class ImageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prompt: str


class NarratorResponse(BaseModel):
    narration: str
    tool_call: ToolCall
    # Sibling to tool_call, not a tool_call variant: an image request has no
    # engine-state effect to execute/log, it's a presentation decision layered
    # on narration - conflating it into the discriminated union above would
    # mix two different kinds of decision the schema is meant to keep apart.
    image_request: ImageRequest | None = None

    # `.tool`/`.tool_args` kept as the external shape every existing caller
    # (server/narration.py, tests) already expects - `tool_args` as a plain
    # dict, same as before the discriminated union - so this fix stays
    # scoped to *what gets validated on the way in*, not every call site.
    @property
    def tool(self) -> str | None:
        return self.tool_call.tool

    @property
    def tool_args(self) -> dict:
        if isinstance(self.tool_call, _NoTool):
            return {}
        return self.tool_call.tool_args.model_dump()


class NarratorClient:
    def __init__(
        self,
        model: str = "qwen3:8b",
        system_prompt: str = "",
        chat_fn: Callable[..., Awaitable[dict]] | None = None,
        generate_fn: Callable[..., Awaitable[object]] | None = None,
    ) -> None:
        self.model = model
        self.system_prompt = system_prompt
        self._client = ollama.AsyncClient(timeout=60)
        self._chat_fn = chat_fn or self._default_chat
        self._generate_fn = generate_fn or self._client.generate

    async def _default_chat(self, *, model: str, messages: list[dict], format: dict) -> dict:
        return await self._client.chat(model=model, messages=messages, format=format)

    async def unload(self) -> None:
        # Ollama's documented way to force-unload a model immediately:
        # generate with keep_alive=0 and no prompt - no inference runs,
        # frees VRAM for an image backend that needs the same GPU.
        await self._generate_fn(model=self.model, keep_alive=0)

    async def respond(self, messages: list[dict]) -> NarratorResponse:
        full_messages = [{"role": "system", "content": self.system_prompt}] + messages
        response = await self._chat_fn(
            model=self.model,
            messages=full_messages,
            format=NarratorResponse.model_json_schema(),
        )
        try:
            return NarratorResponse.model_validate_json(response["message"]["content"])
        except ValidationError as e:
            raise ValueError(f"model returned invalid structured output: {e}") from e
