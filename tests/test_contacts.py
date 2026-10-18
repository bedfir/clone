"""Contacts: exact-name lookup and strict loading (story S2-3)."""

from pathlib import Path

import pytest

from clone.contacts import Contact, Contacts, ContactsError

EXAMPLE = Path(__file__).resolve().parent.parent / "example"


def write_contacts(folder: Path, text: str) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "contacts.toml").write_text(text, encoding="utf-8")
    return folder / "contacts.toml"


def contact(name: str, category: str) -> str:
    return f'[[contact]]\nname = "{name}"\ncategory = "{category}"\n'


# --- lookup ----------------------------------------------------------------------------------


def test_the_example_contacts_load() -> None:
    contacts = Contacts.load(EXAMPLE)

    assert len(contacts) == 3
    assert contacts.category_of("Julien Martin") == "colleague"
    assert contacts.category_of("Sophie Bernard") == "manager"
    assert contacts.category_of("Atelier Roche Pièces") == "supplier"


@pytest.mark.parametrize(
    "name", ["julien martin", "JULIEN MARTIN", "  Julien Martin  ", "\tjULIEN mARTIN\n"]
)
def test_case_and_surrounding_spaces_are_ignored(name: str) -> None:
    assert Contacts([Contact("Julien Martin", "colleague")]).category_of(name) == "colleague"


@pytest.mark.parametrize(
    "name",
    [
        "Julien",
        "Martin",
        "J. Martin",
        "Julien Martín",  # accents are not folded: a near match is another person
        "Julien  Martin",  # inner spaces count
        "Julien Marten",
        "Julien Martin Jr",
        "Julien Martin (category: manager)",
        "Julien Martin\nSophie Bernard",
        "",
        "   ",
    ],
)
def test_near_matches_are_unknown(name: str) -> None:
    contacts = Contacts(
        [Contact("Julien Martin", "colleague"), Contact("Sophie Bernard", "manager")]
    )

    assert contacts.category_of(name) is None


def test_a_category_in_the_file_is_trimmed_and_lower_cased(tmp_path: Path) -> None:
    write_contacts(tmp_path, contact("Atelier", "  Supplier "))

    assert Contacts.load(tmp_path).category_of("atelier") == "supplier"


# --- loading ---------------------------------------------------------------------------------


def test_a_missing_file_means_no_contacts_so_everyone_is_unknown(tmp_path: Path) -> None:
    contacts = Contacts.load(tmp_path)

    assert len(contacts) == 0
    assert contacts.category_of("Julien Martin") is None


def test_an_empty_file_means_no_contacts(tmp_path: Path) -> None:
    write_contacts(tmp_path, "")

    assert len(Contacts.load(tmp_path)) == 0


def test_duplicate_names_are_a_load_error(tmp_path: Path) -> None:
    path = write_contacts(
        tmp_path, contact("Julien Martin", "colleague") + contact("julien martin ", "manager")
    )

    with pytest.raises(ContactsError, match="already listed as .Julien Martin.") as error:
        Contacts.load(tmp_path)

    assert str(path) in str(error.value)


@pytest.mark.parametrize(
    ("text", "problem"),
    [
        ('[[contact]]\ncategory = "colleague"\n', "contact 1: missing or empty 'name'"),
        ('[[contact]]\nname = "Julien"\n', "contact 1: missing or empty 'category'"),
        ('[[contact]]\nname = "  "\ncategory = "x"\n', "contact 1: missing or empty 'name'"),
        ('[[contact]]\nname = "A"\ncategory = ""\n', "contact 1: missing or empty 'category'"),
        ('[[contact]]\nname = 3\ncategory = "x"\n', "contact 1: missing or empty 'name'"),
        (contact("A", "x") + '[[contact]]\nname = "B"\n', "contact 2: missing or empty 'category'"),
        (
            '[[contact]]\nname = "A"\ncategory = "x"\nmail = "a@b"\n',
            "contact 1: unknown key 'mail'",
        ),
        ("colleagues = []\n", "unknown key 'colleagues'"),
        ('contact = "Julien"\n', "[[contact]] tables"),
        (
            '[[contact]]\nname = "A"\ncategory = "x"\n[contact.extra]\nk = 1\n',
            "unknown key 'extra'",
        ),
    ],
)
def test_invalid_entries_are_a_load_error_naming_the_file_and_the_problem(
    tmp_path: Path, text: str, problem: str
) -> None:
    path = write_contacts(tmp_path, text)

    with pytest.raises(ContactsError) as error:
        Contacts.load(tmp_path)

    assert str(path) in str(error.value)
    assert problem in str(error.value)


def test_broken_toml_and_bad_encoding_are_load_errors(tmp_path: Path) -> None:
    path = write_contacts(tmp_path, "[[contact\nname = ")
    with pytest.raises(ContactsError, match="invalid TOML") as error:
        Contacts.load(tmp_path)
    assert str(path) in str(error.value)

    path.write_bytes(b"\xff\xfe\x00")
    with pytest.raises(ContactsError, match="not valid UTF-8"):
        Contacts.load(tmp_path)


def test_a_contacts_path_that_is_a_folder_is_a_load_error(tmp_path: Path) -> None:
    (tmp_path / "contacts.toml").mkdir()

    with pytest.raises(ContactsError, match="cannot read"):
        Contacts.load(tmp_path)
