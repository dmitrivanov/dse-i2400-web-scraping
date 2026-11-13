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


def test_scraper_configuration(monkeypatch):
    monkeypatch.setenv("SCRAPER_API_KEY", "fixture-key")
    monkeypatch.setenv("SCRAPER_API_BASE_URL", "https://api.scraperapi.com")
    assert config.get_scraper_config()["base_url"] == "https://api.scraperapi.com"


@pytest.mark.parametrize("url", ["http://api.scraperapi.com", "https://other.example", "https://api.scraperapi.com/structured", "https://api.scraperapi.com:secret"])
def test_reject_scraper_endpoint(monkeypatch, url):
    monkeypatch.setenv("SCRAPER_API_KEY", "fixture-key")
    monkeypatch.setenv("SCRAPER_API_BASE_URL", url)
    with pytest.raises(ValueError) as error:
        config.get_scraper_config()
    assert "secret" not in str(error.value)


def test_missing_scraper_key(monkeypatch):
    monkeypatch.delenv("SCRAPER_API_KEY", raising=False)
    with pytest.raises(ValueError, match="SCRAPER_API_KEY"):
        config.get_scraper_config()
