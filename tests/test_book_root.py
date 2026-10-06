import pytest

from family_cookbook.config import BookRoot, ConfigError, find_root


@pytest.fixture
def book(tmp_path):
    (tmp_path / "book" / "recipes" / "mains").mkdir(parents=True)
    (tmp_path / "book" / "book.yaml").write_text("book:\n  title: T\n", encoding="utf-8")
    return tmp_path


def test_finds_root_at_start(book):
    assert find_root(book) == BookRoot(book.resolve())


def test_finds_root_from_a_folder_below(book):
    assert find_root(book / "book" / "recipes" / "mains").path == book.resolve()


def test_book_folder_without_config_is_not_a_root(tmp_path):
    (tmp_path / "book").mkdir()
    with pytest.raises(ConfigError, match="no book/book.yaml"):
        find_root(tmp_path)
