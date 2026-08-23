import argparse
import asyncio
from dataclasses import dataclass, field

from narrator.client import NarratorClient, NarratorResponse


@dataclass
class Scenario:
    name: str
    messages: list[dict]
    expected_tool: str | None


@dataclass
class ScenarioResult:
    passes: int = 0
    total: int = 0


@dataclass
class HarnessReport:
    results: dict[str, ScenarioResult] = field(default_factory=dict)


def _scores_as_pass(response: NarratorResponse, expected_tool: str | None) -> bool:
    # tool_args is now validated against the real per-tool schema at parse
    # time (NarratorClient.respond() raises before a response with the
    # wrong argument shape ever reaches here) - re-validating it a second
    # time here would be dead code checking something that can no longer
    # be false by the time a response object exists at all.
    return response.tool == expected_tool


async def run_harness(client: NarratorClient, scenarios: list[Scenario], repeat: int) -> HarnessReport:
    report = HarnessReport()
    for scenario in scenarios:
        result = ScenarioResult()
        for _ in range(repeat):
            result.total += 1
            try:
                response = await client.respond(scenario.messages)
            except ValueError:
                # A response that fails schema validation (wrong tool_args
                # shape, hallucinated tool name, malformed JSON) is exactly
                # the kind of miss this harness exists to measure - score
                # it as a failed rep, don't let it crash the whole run.
                continue
            if _scores_as_pass(response, scenario.expected_tool):
                result.passes += 1
        report.results[scenario.name] = result
    return report


DEFAULT_SCENARIOS: list[Scenario] = [
    Scenario(
        name="risky_physical_action_calls_request_roll",
        messages=[{"role": "user", "content": "I try to leap across the rooftop gap before the drone spots me."}],
        expected_tool="request_roll",
    ),
    Scenario(
        name="idle_observation_has_no_tool_call",
        messages=[{"role": "user", "content": "I look around the room."}],
        expected_tool=None,
    ),
    Scenario(
        name="taking_damage_calls_apply_character_update",
        messages=[{"role": "system", "content": "The player was just hit by gunfire for 4 damage."},
                   {"role": "user", "content": "I stagger back, bleeding."}],
        expected_tool="apply_character_update",
    ),
    Scenario(
        name="entering_a_new_location_calls_update_world",
        messages=[{"role": "user", "content": "I head into the Afterlife bar."}],
        expected_tool="update_world",
    ),
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the narrator reliability harness against a live model.")
    parser.add_argument("--repeat", type=int, default=5)
    parser.add_argument("--model", type=str, default="qwen3:8b")
    parser.add_argument("--system-prompt", type=str, default="You are a cyberpunk tabletop game master.")
    args = parser.parse_args()

    client = NarratorClient(model=args.model, system_prompt=args.system_prompt)
    report = asyncio.run(run_harness(client, DEFAULT_SCENARIOS, args.repeat))

    for name, result in report.results.items():
        rate = result.passes / result.total if result.total else 0.0
        print(f"{name}: {result.passes}/{result.total} ({rate:.0%})")


if __name__ == "__main__":
    main()
