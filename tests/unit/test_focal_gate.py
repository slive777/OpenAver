"""TASK-98a-T3: core/focal/gate.py — requires_face_detection / gate_verdict.

Acts on OpenAver canonical `videos.number` + `videos.maker` — never on
filenames, never via trim(). See feature/98-focal-crop/TASK-98a-T3.md for
the DoD list and the deliberate divergence (num-alpha rule dropped).
"""
import pytest

from core.focal.gate import (
    _UNCENSORED_MAKERS_LC,
    gate_verdict,
    requires_face_detection,
)


# ---- DoD-1: [4SSIS-296] regression lock ------------------------------------

@pytest.mark.parametrize("number", ["SSIS-296", "4SSIS-296"])
def test_censored_regression_lock(number):
    assert requires_face_detection(number) is False


# ---- DoD-2: real uncensored numbers -> True --------------------------------

@pytest.mark.parametrize("number", [
    "FC2-1234567",
    "FC2-PPV-1234567",
    "200GANA-1234",
    "259LUXU-1234",
    "SIRO-1234",
    "HEYZO-1234",
    "022509-995",
    "010119_001",
    "N0893",
])
def test_real_uncensored_hits_true(number):
    assert requires_face_detection(number) is True


# ---- DoD-3: maker whitelist -------------------------------------------------

@pytest.mark.parametrize("maker", ["Caribbeancom", "1Pondo"])
def test_maker_whitelist_true_when_number_no_match(maker):
    # number doesn't match any number-based rule; maker whitelist saves it.
    assert requires_face_detection("ABC-123", maker) is True


def test_censored_number_with_censored_maker_false():
    assert requires_face_detection("SSIS-296", "S1") is False


def test_empty_maker_with_censored_number_false():
    assert requires_face_detection("SSIS-296", "") is False


# ---- DoD-4: digit-prefixed censored -> False (drop num_alpha) -------------

@pytest.mark.parametrize("number", [
    "7IPZ-154",
    "3ABW-001",
    "1SDMS-00808",
    "3DSVR-123",
])
def test_digit_prefixed_censored_stays_false(number):
    assert requires_face_detection(number) is False


# ---- DoD-5: empty-input tolerance ------------------------------------------

def test_empty_string_number_no_raise():
    assert requires_face_detection("") is False


def test_none_number_no_raise():
    assert requires_face_detection(None) is False


def test_none_maker_no_raise():
    assert requires_face_detection("SSIS-296", None) is False


def test_none_number_with_whitelisted_maker():
    assert requires_face_detection(None, "Caribbeancom") is True


def test_none_number_none_maker():
    assert requires_face_detection(None, None) is False


# ---- DoD-6: SSOT import sanity ----------------------------------------------

def test_uncensored_makers_lc_sourced_from_ssot():
    from core.scrapers.utils import METATUBE_UNCENSORED
    assert _UNCENSORED_MAKERS_LC == {m.lower() for m in METATUBE_UNCENSORED}
    assert 'caribbeancom' in _UNCENSORED_MAKERS_LC
    assert '1pondo' in _UNCENSORED_MAKERS_LC


# ---- gate_verdict reason strings -------------------------------------------

def test_gate_verdict_censored_reason():
    requires, reason = gate_verdict("SSIS-296", "S1")
    assert requires is False
    assert reason == 'censored/standard -> right-crop'


def test_gate_verdict_fc2_reason():
    requires, reason = gate_verdict("FC2-1234567")
    assert requires is True
    assert reason == 'FC2'


def test_gate_verdict_uncensored_reason():
    requires, reason = gate_verdict("HEYZO-1234")
    assert requires is True
    assert reason == 'uncensored'


def test_gate_verdict_shirouto_reason():
    requires, reason = gate_verdict("200GANA-1234")
    assert requires is True
    assert reason == 'shirouto/amateur'


def test_gate_verdict_maker_whitelist_reason():
    requires, reason = gate_verdict("ABC-123", "Caribbeancom")
    assert requires is True
    assert reason == 'maker-whitelist'


def test_gate_verdict_empty_number_censored_maker():
    requires, reason = gate_verdict("", "S1")
    assert requires is False
    assert reason == 'censored/standard -> right-crop'


def test_gate_verdict_empty_number_whitelisted_maker():
    requires, reason = gate_verdict(None, "1Pondo")
    assert requires is True
    assert reason == 'maker-whitelist'


# Note: DoD-7 mutation testing (temporarily re-adding a num-alpha rule /
# neutering _SHIROUTO_RE against the real core/focal/gate.py, confirming
# RED, then reverting) was performed manually as a one-off verification
# pass -- see TASK-98a-T3 completion report. It is not encoded as a
# permanent test here because mutating the SUT in-place inside the
# committed suite would defeat the point (the mutation must be reverted
# for the suite to reflect shipped behavior).
