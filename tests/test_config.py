import pytest

import config


@pytest.fixture(autouse=True)
def database_environment(monkeypatch):
    monkeypatch.setattr(config, "load_dotenv", lambda *args: None)
    for name, value in {"DB_HOST": "localhost", "DB_USER": "student",
                        "DB_NAME": "MY_CUSTOM_BOT", "DB_PASSWORD": ""}.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("DB_PORT", raising=False)


def test_configuration():
    assert config.get_database_config() == {
        "host": "localhost", "port": 3306, "user": "student",
        "password": "", "database": "MY_CUSTOM_BOT"}


@pytest.mark.parametrize("name", ["DB_HOST", "DB_USER", "DB_NAME", "DB_PASSWORD"])
def test_missing_setting(monkeypatch, name):
    monkeypatch.delenv(name)
    with pytest.raises(ValueError, match=name):
        config.get_database_config()


@pytest.mark.parametrize("port", ["abc", "0", "65536"])
def test_invalid_port(monkeypatch, port):
    monkeypatch.setenv("DB_PORT", port)
    with pytest.raises(ValueError, match="DB_PORT"):
        config.get_database_config()


def test_environment_overrides_dotenv(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("DB_HOST=filehost\nDB_PORT=3307\n")
    from dotenv import load_dotenv
    monkeypatch.setattr(config, "load_dotenv", lambda *args: load_dotenv(env_file))
    assert config.get_database_config()["host"] == "localhost"
    assert config.get_database_config()["port"] == 3307
