"""
Tests for _version_gt, the comparison the update check relies on to decide
whether a newly published release is actually newer than the running build.
Covers equal versions, each side newer, differing segment counts, and
non-numeric or malformed input, matching the function's real (numeric-only,
zero-padded) comparison rather than assumed semver behaviour.
"""

import simple_una_device_manager as app


def test_equal_versions_are_not_greater():
    assert app._version_gt("1.4.2", "1.4.2") is False


def test_left_side_newer():
    assert app._version_gt("1.4.3", "1.4.2") is True
    assert app._version_gt("2.0.0", "1.9.9") is True


def test_right_side_newer():
    assert app._version_gt("1.4.1", "1.4.2") is False
    assert app._version_gt("1.9.9", "2.0.0") is False


def test_differing_segment_counts_are_zero_padded():
    # Missing trailing segments are treated as 0, not ignored.
    assert app._version_gt("1.4", "1.4.0") is False
    assert app._version_gt("1.4.1", "1.4") is True
    assert app._version_gt("1.4", "1.4.1") is False


def test_dash_separated_segments_are_also_compared():
    assert app._version_gt("1.4.3-1", "1.4.3-0") is True


def test_non_numeric_segments_are_treated_as_zero():
    # A non-digit segment (e.g. a pre-release tag) becomes 0, not a
    # meaningful comparison value: "beta" here contributes 0, not "greater".
    assert app._version_gt("1.2.3", "1.2.3-beta") is False
    assert app._version_gt("1.2.3-beta", "1.2.3") is False


def test_malformed_leading_text_zeroes_that_segment():
    # A segment that mixes letters and digits (e.g. a "v" prefix that wasn't
    # stripped) fails isdigit() entirely and is treated as 0.
    assert app._version_gt("v2.0.0", "1.9.9") is False


def test_empty_string_is_never_newer():
    assert app._version_gt("", "1.0.0") is False
    assert app._version_gt("1.0.0", "") is True
