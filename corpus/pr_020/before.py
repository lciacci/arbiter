"""Tests for config loading."""
from flask import Flask


def test_from_object_loads_uppercase():
    app = Flask(__name__)

    class C:
        DEBUG = True
        SECRET = "abc"
        lowercase = "ignored"

    app.config.from_object(C)
    assert app.config["DEBUG"] is True
    assert app.config["SECRET"] == "abc"
    assert "lowercase" not in app.config


def test_from_mapping_basic():
    app = Flask(__name__)
    app.config.from_mapping({"FOO": 1, "BAR": 2})
    assert app.config["FOO"] == 1
    assert app.config["BAR"] == 2
