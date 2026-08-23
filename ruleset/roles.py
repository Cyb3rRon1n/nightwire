from dataclasses import dataclass

from ruleset.attributes import Attribute


@dataclass(frozen=True)
class Role:
    name: str
    primary_attribute: Attribute
    description: str


ROLES: dict[str, Role] = {
    "solo": Role(
        name="Solo",
        primary_attribute=Attribute.REFLEXES,
        description=(
            "Front-line combat specialist. Best attack rolls, highest "
            "Health, a passive Initiative/Awareness edge."
        ),
    ),
    "netrunner": Role(
        name="Netrunner",
        primary_attribute=Attribute.TECH,
        description=(
            "Hacking specialist. Bypasses locks, pulls data, and disables "
            "weapons/cameras/drones mid-combat."
        ),
    ),
    "techie": Role(
        name="Techie",
        primary_attribute=Attribute.TECH,
        description=(
            "Gear specialist. Repairs damaged equipment and cyberware, "
            "installs upgrades, crafts - keeps the party's equipment "
            "working, not a healer."
        ),
    ),
    "fixer": Role(
        name="Fixer",
        primary_attribute=Attribute.PRESENCE,
        description=(
            "Social specialist. Negotiation, contacts, contraband access - "
            "talks past trouble instead of shooting through it."
        ),
    ),
}
