# Tests for BullBot offline demo mode.
# These run with NO AWS credentials and NO network: demo mode is forced on, and boto3
# is sabotaged so any accidental AWS client creation fails the test loudly.

import importlib
import os
import sys

import pytest

WEB_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "web")
sys.path.insert(0, WEB_DIR)


# Force demo mode and block all AWS client creation for every test in this module.
@pytest.fixture(autouse=True)
def offline_env(monkeypatch):
    monkeypatch.setenv("BULLBOT_DEMO_MODE", "1")
    monkeypatch.delenv("BULLBOT_KB_ID", raising=False)
    monkeypatch.delenv("BULLBOT_GUARDRAIL_ID", raising=False)

    # Any boto3.client(...) call during demo mode is a bug; make it explode.
    import boto3

    def _boom(*args, **kwargs):
        raise AssertionError("AWS client created in demo mode - no AWS calls allowed")

    monkeypatch.setattr(boto3, "client", _boom)

    # Reload core so it picks up the forced env and patched boto3.
    import bullbot_core
    importlib.reload(bullbot_core)
    return bullbot_core


def test_demo_mode_detected(offline_env):
    assert offline_env.demo_mode_enabled() is True


def test_transfer_credits_answer_has_citation(offline_env):
    answer, session, blocked = offline_env.ask(None, None, None,
                                               "Do my community college credits transfer?")
    assert blocked is False
    assert "assist-articulation-cc-to-sacstate-cs.md" in answer
    assert session is None  # demo mode has no Bedrock session


def test_cal_grant_b_answer(offline_env):
    answer, _, blocked = offline_env.ask(None, None, None,
                                         "What are the Cal Grant B renewal requirements?")
    assert blocked is False
    assert "financial-aid-cal-grant-b-policy.md" in answer


def test_data_science_minor_answer(offline_env):
    answer, _, blocked = offline_env.ask(None, None, None,
                                         "Plan to add a Data Science minor without delaying graduation")
    assert blocked is False
    assert "data-science-minor-requirements.md" in answer


def test_spanish_answer(offline_env):
    answer, _, blocked = offline_env.ask(None, None, None,
                                         "Mis creditos del colegio comunitario cuentan?")
    assert blocked is False
    assert "Fuentes" in answer  # answered in Spanish


def test_pii_is_blocked(offline_env):
    answer, _, blocked = offline_env.ask(None, None, None, "My SSN is 123-45-6789")
    assert blocked is True
    assert "privacy" in answer.lower()


def test_offtopic_is_blocked(offline_env):
    answer, _, blocked = offline_env.ask(None, None, None,
                                         "Who won the Kings game last night?")
    assert blocked is True
    assert "Sac State" in answer


def test_unknown_question_gets_fallback(offline_env):
    answer, _, blocked = offline_env.ask(None, None, None,
                                         "What is the airspeed velocity of a swallow?")
    assert blocked is False
    assert "Demo Mode" in answer
