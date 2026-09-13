import string

import password_generator


def test_scrambled_generator_has_requested_shape(monkeypatch):
    settings = {
        "letters_count": 20,
        "numbers_count": 4,
        "symbols_count": 3,
    }
    result = password_generator._generate_scrambled(settings)

    assert len(result) == 27
    assert sum(character in string.ascii_letters for character in result) == 20
    assert sum(character.isdigit() for character in result) == 4
    assert sum(character in string.punctuation for character in result) == 3
