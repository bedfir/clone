"""Contacts: who the owner's people are, and the category of each.

`data/contacts.toml`:

    [[contact]]
    name = "Julien Martin"
    category = "colleague"

The category of a recipient always comes from this file, never from the model. Lookup is by
exact name (trimmed, case-insensitive): no fuzzy matching, because a near match could reach
the wrong person. Anything not listed is an unknown recipient.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from clone.tomlfile import read_toml

CONTACTS_FILE = "contacts.toml"
_CONTACT_KEYS = {"name", "category"}


class ContactsError(Exception):
    """The contacts file is invalid; the message names the file and the problem."""


def normalize(text: str) -> str:
    """Trim and ignore case. Nothing else: accents, inner spaces and spelling must match."""
    return text.strip().casefold()


@dataclass(frozen=True)
class Contact:
    name: str
    category: str  # normalized, so that it compares with the policy's categories


class Contacts:
    """The owner's contacts, by exact name."""

    def __init__(self, contacts: Iterable[Contact] = ()) -> None:
        self._by_name: dict[str, Contact] = {}
        for contact in contacts:
            key = normalize(contact.name)
            if key in self._by_name:
                raise ContactsError(
                    f"Duplicate contact name {contact.name!r}: already listed as "
                    f"{self._by_name[key].name!r} (case is ignored)."
                )
            self._by_name[key] = contact

    def __len__(self) -> int:
        return len(self._by_name)

    def category_of(self, name: str) -> str | None:
        """The category of the contact called exactly `name`, or None if unknown."""
        contact = self._by_name.get(normalize(name))
        return contact.category if contact else None

    @classmethod
    def load(cls, data_dir: str | Path) -> Contacts:
        """Load `<data_dir>/contacts.toml`. A missing file means no contacts at all."""
        path = Path(data_dir) / CONTACTS_FILE
        data = read_toml(path, ContactsError)
        if data is None:
            return cls()
        for key in data:
            if key != "contact":
                raise ContactsError(f"{path}: unknown key {key!r}. Only [[contact]] is allowed.")
        entries = data.get("contact", [])
        if not isinstance(entries, list) or not all(isinstance(e, dict) for e in entries):
            raise ContactsError(f"{path}: contacts must be written as [[contact]] tables.")

        contacts = []
        for number, entry in enumerate(entries, 1):
            for key in entry:
                if key not in _CONTACT_KEYS:
                    raise ContactsError(f"{path}: contact {number}: unknown key {key!r}.")
            for key in sorted(_CONTACT_KEYS):
                value = entry.get(key)
                if not isinstance(value, str) or not value.strip():
                    raise ContactsError(f"{path}: contact {number}: missing or empty {key!r}.")
            contacts.append(Contact(entry["name"].strip(), normalize(entry["category"])))
        try:
            return cls(contacts)
        except ContactsError as problem:
            raise ContactsError(f"{path}: {problem}") from None
