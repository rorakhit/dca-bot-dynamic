from unittest.mock import MagicMock, patch


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
