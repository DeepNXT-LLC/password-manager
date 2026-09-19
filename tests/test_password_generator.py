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


def test_get_password_settings_defaults_include_reminder_days():
    settings = password_generator.get_password_settings()

    assert "reminder_days" in settings
    assert settings["reminder_days"] in (30, 60, 90, "off")


def test_update_password_settings_accepts_off_for_reminders(tmp_path, monkeypatch):
    monkeypatch.setattr(password_generator, "PRIVATE_CONFIG_PATH", str(tmp_path / "private_config.json"))
    monkeypatch.setattr(password_generator, "PUBLIC_CONFIG_PATH", str(tmp_path / "public_config.json"))
    saved = password_generator.update_password_settings({"reminder_days": "off"})

    assert saved["reminder_days"] == "off"
