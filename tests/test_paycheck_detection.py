import pytest


@pytest.fixture(autouse=True)
def patch_config(monkeypatch):
    import config
    monkeypatch.setattr(config, "PAYCHECK_EMPLOYER_KEYWORD", "DATALIGN ADVISOR")
    monkeypatch.setattr(config, "PAYCHECK_MIN_AMOUNT", 575.00)


def test_detects_paycheck():
    from plaid_client import is_paycheck
    txn = {"transaction_id": "t1", "amount": -1575.00, "name": "DATALIGN ADVISOR PAYROLL"}
    assert is_paycheck(txn) is True


def test_rejects_amount_too_small():
    from plaid_client import is_paycheck
    txn = {"transaction_id": "t2", "amount": -100.00, "name": "DATALIGN ADVISOR PAYROLL"}
    assert is_paycheck(txn) is False


def test_rejects_debit_transaction():
    from plaid_client import is_paycheck
    txn = {"transaction_id": "t3", "amount": 1575.00, "name": "DATALIGN ADVISOR PAYROLL"}
    assert is_paycheck(txn) is False


def test_rejects_wrong_employer():
    from plaid_client import is_paycheck
    txn = {"transaction_id": "t4", "amount": -2000.00, "name": "SOME OTHER COMPANY PAYROLL"}
    assert is_paycheck(txn) is False


def test_case_insensitive_match():
    from plaid_client import is_paycheck
    txn = {"transaction_id": "t5", "amount": -900.00, "name": "datalign advisor direct dep"}
    assert is_paycheck(txn) is True


def test_exact_minimum_amount_qualifies():
    from plaid_client import is_paycheck
    txn = {"transaction_id": "t6", "amount": -575.00, "name": "DATALIGN ADVISOR PAYROLL"}
    assert is_paycheck(txn) is True


def test_just_below_minimum_rejected():
    from plaid_client import is_paycheck
    txn = {"transaction_id": "t7", "amount": -574.99, "name": "DATALIGN ADVISOR PAYROLL"}
    assert is_paycheck(txn) is False
