from datetime import date
from unittest.mock import MagicMock, patch

import pytest


# ── _expected_pay_dates / _is_near_pay_date ──────────────────────────────────

def test_pay_dates_normal_weekday():
    from plaid_client import _expected_pay_dates
    # 2026-04-15 is a Wednesday, 2026-04-30 is a Thursday — no adjustment
    pay_dates = _expected_pay_dates(date(2026, 4, 15))
    assert date(2026, 4, 15) in pay_dates
    assert date(2026, 4, 30) in pay_dates


def test_pay_dates_saturday_shifts_to_friday():
    from plaid_client import _expected_pay_dates
    # 2026-05-15 is a Friday — no shift. 2026-05-31 is a Sunday → Friday May 29
    pay_dates = _expected_pay_dates(date(2026, 5, 31))
    assert date(2026, 5, 29) in pay_dates  # Sunday → Friday


def test_pay_dates_sunday_shifts_to_friday():
    from plaid_client import _expected_pay_dates
    # 2026-11-15 is a Sunday → Friday Nov 13
    pay_dates = _expected_pay_dates(date(2026, 11, 15))
    assert date(2026, 11, 13) in pay_dates


def test_is_near_pay_date_within_window():
    from plaid_client import _is_near_pay_date
    assert _is_near_pay_date(date(2026, 4, 15))   # exact
    assert _is_near_pay_date(date(2026, 4, 13))   # 2 days before
    assert _is_near_pay_date(date(2026, 4, 17))   # 2 days after
    assert _is_near_pay_date(date(2026, 4, 30))   # exact end of month


def test_is_near_pay_date_outside_window():
    from plaid_client import _is_near_pay_date
    assert not _is_near_pay_date(date(2026, 4, 10))  # 5 days before 15th
    assert not _is_near_pay_date(date(2026, 4, 20))  # mid-month, nowhere near


# ── is_paycheck ───────────────────────────────────────────────────────────────

def _txn(amount=-1200.0, name="DATALIGN ADVISOR PAYROLL", txn_date="2026-04-15"):
    return {"amount": amount, "name": name, "date": txn_date}


def test_is_paycheck_valid():
    from plaid_client import is_paycheck
    assert is_paycheck(_txn())


def test_is_paycheck_wrong_keyword():
    from plaid_client import is_paycheck
    assert not is_paycheck(_txn(name="RANDOM DEPOSIT"))


def test_is_paycheck_too_small():
    from plaid_client import is_paycheck
    assert not is_paycheck(_txn(amount=-100.0))


def test_is_paycheck_positive_amount():
    from plaid_client import is_paycheck
    assert not is_paycheck(_txn(amount=1200.0))


def test_is_paycheck_wrong_date():
    from plaid_client import is_paycheck
    assert not is_paycheck(_txn(txn_date="2026-04-20"))  # mid-month


def test_is_paycheck_end_of_month():
    from plaid_client import is_paycheck
    assert is_paycheck(_txn(txn_date="2026-04-30"))


def test_is_paycheck_no_date_still_passes():
    from plaid_client import is_paycheck
    txn = {"amount": -1200.0, "name": "DATALIGN ADVISOR PAYROLL"}
    assert is_paycheck(txn)  # missing date skips the window check


# ── get_account_info ──────────────────────────────────────────────────────────

def test_get_account_info_returns_institution_and_mask():
    mock_item_response = MagicMock()
    mock_item_response.item.institution_id = "ins_3"

    mock_institution_response = MagicMock()
    mock_institution_response.institution.name = "Chase"

    mock_accounts_response = MagicMock()
    mock_account = MagicMock()
    mock_account.mask = "4521"
    mock_accounts_response.accounts = [mock_account]

    with patch("plaid_client.plaid_client") as mock_client:
        mock_client.item_get.return_value = mock_item_response
        mock_client.institutions_get_by_id.return_value = mock_institution_response
        mock_client.accounts_get.return_value = mock_accounts_response

        from plaid_client import get_account_info
        name, mask = get_account_info("access-sandbox-abc123")

    assert name == "Chase"
    assert mask == "4521"
