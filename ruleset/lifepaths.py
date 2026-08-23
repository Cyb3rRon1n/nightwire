from dataclasses import dataclass


@dataclass(frozen=True)
class Lifepath:
    name: str
    description: str


LIFEPATHS: dict[str, Lifepath] = {
    "corpo": Lifepath(
        name="Corpo",
        description=(
            "Came from megacorp life - contacts inside corporate "
            "structures, insider knowledge, expects to be listened to."
        ),
    ),
    "streetkid": Lifepath(
        name="Streetkid",
        description=(
            "Grew up in the sprawl - gang contacts, street cred, knows "
            "how things really work at ground level."
        ),
    ),
    "nomad": Lifepath(
        name="Nomad",
        description=(
            "Raised outside the city in a clan/family - vehicle know-how, "
            "an outsider's read on the corps, strong found-family loyalty."
        ),
    ),
}
