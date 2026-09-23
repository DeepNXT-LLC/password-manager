"""Synthetic UI error-path checks without opening a desktop window."""

import pytest

import password_manager as pm


class FakeVar:
    def __init__(self):
        self.value = ""

    def set(self, value):
        self.value = value

    def get(self):
        return self.value


@pytest.mark.parametrize("failure", [
    ValueError("SYNTHETIC_SECRET: weak settings"),
    FileNotFoundError("SYNTHETIC_SECRET: word list path"),
])
@pytest.mark.parametrize("preview", [False, True])
def test_generator_validation_failure_shows_safe_guidance(monkeypatch, failure, preview):
    app = object.__new__(pm.PasswordManagerApp)
    app.tabs = {"password_book": {"password_var": FakeVar()}}
    app.settings_preview_var = FakeVar()
    warnings = []
    monkeypatch.setattr(pm.password_generator, "generate_password", lambda: (_ for _ in ()).throw(failure))
    monkeypatch.setattr(pm.messagebox, "showwarning", lambda title, message: warnings.append((title, message)))

    if preview:
        app.generate_settings_preview()
        assert app.settings_preview_var.get() == ""
    else:
        app.generate_and_fill_password("password_book")
        assert app.tabs["password_book"]["password_var"].get() == ""

    assert len(warnings) == 1
    assert warnings[0][0] == "Generator Settings"
    assert "Settings" in warnings[0][1]
    assert "SYNTHETIC_SECRET" not in warnings[0][1]


def test_missing_vault_can_cancel_restore_before_master_password_prompt(tmp_path, monkeypatch):
    (tmp_path / ".password-vault-initialized").write_text("initialized\n", encoding="ascii")
    monkeypatch.setattr(pm, "BASE_DIR", str(tmp_path))

    class FakeRoot:
        destroyed = False

        def withdraw(self):
            pass

        def destroy(self):
            self.destroyed = True

    root = FakeRoot()
    questions = []
    monkeypatch.setattr(pm.tk, "Tk", lambda: root)
    monkeypatch.setattr(pm.messagebox, "askyesno", lambda *args, **kwargs: questions.append(args) or False)
    monkeypatch.setattr(pm.simpledialog, "askstring", lambda *args, **kwargs: pytest.fail("prompted for a new master password"))

    pm.main()

    assert root.destroyed
    assert len(questions) == 1
    assert questions[0][0] == "Vault Missing"
    assert not (tmp_path / "json_files" / "password_data.vault").exists()


def test_missing_vault_ui_restores_full_backup_without_empty_intermediate(tmp_path, monkeypatch):
    master = "synthetic-master-password-123"
    monkeypatch.setattr(pm, "BASE_DIR", str(tmp_path))
    manager = pm.StorageManager(master)
    manager.add_record("password_book", {
        "employee_name": "Synthetic", "account_name": "Account", "username": "user",
        "account_password": "synthetic-value", "notes": "",
    })
    backup = tmp_path / "full.vault"
    manager.export_all_records_to_file(str(backup))
    vault = tmp_path / "json_files" / "password_data.vault"
    vault.rename(tmp_path / "synthetic-quarantine.vault")

    class FakeRoot:
        def withdraw(self):
            pass

        def deiconify(self):
            self.visible = True

        def mainloop(self):
            pass

        def destroy(self):
            pytest.fail("The restore workflow aborted")

    root = FakeRoot()
    prompts = []
    monkeypatch.setattr(pm.tk, "Tk", lambda: root)
    monkeypatch.setattr(pm.messagebox, "askyesno", lambda *args, **kwargs: True)
    monkeypatch.setattr(pm.filedialog, "askopenfilename", lambda *args, **kwargs: str(backup))
    monkeypatch.setattr(pm.simpledialog, "askstring", lambda *args, **kwargs: prompts.append(args[0]) or master)
    monkeypatch.setattr(pm.messagebox, "showinfo", lambda *args, **kwargs: None)
    monkeypatch.setattr(pm.PasswordManagerApp, "__init__", lambda self, _root, _master: None)

    pm.main()

    assert prompts == ["Unlock Backup"]
    assert root.visible
    assert pm.StorageManager(master).fetch_records("password_book")[0]["account_password"] == "synthetic-value"
