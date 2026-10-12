from decimal import Decimal
from beanbot.services.agent.confidence import account_confidence


def test_history_frequency_is_explainable_and_cold_start_asks():
    history = [('火锅', 'Assets:WeChat:Balance')] * 6 + [('火锅', 'Liabilities:CreditCard')] * 2
    evidence = account_confidence('火锅', history)
    assert evidence[0].ratio == Decimal('0.75')
    assert evidence[0].label == 'Assets:WeChat:Balance 6/8'
    assert account_confidence('新商户', history) == []


async def test_candidates_rank_merchant_then_global_and_limit(tmp_path):
    from tests.test_pending_writes import prepared, transaction
    from beanbot.services.agent.accounts import candidates

    _, user, ledgers = prepared(tmp_path)
    ledger = ledgers.get(user)
    await ledger.insert([transaction(payee='商户').model_copy(update={'from_account': 'Assets:Cash'})] + [transaction(payee='别家')] * 3)
    options = candidates(ledger, {'payee': '商户', 'to_account': 'Expenses:Food:Dining'}, 'from_account', 2)
    assert options == [{'account': 'Assets:Cash', 'display_name': '现金'},
                       {'account': 'Assets:WeChat:Balance', 'display_name': '微信'}]
    assert len(options) == 2
    cold = candidates(ledger, {'payee': '新商户', 'to_account': 'Expenses:Food:Dining'}, 'from_account', 12)
    assert cold[0]['account'] == 'Assets:WeChat:Balance'
    assert all(item['account'].startswith(('Assets:', 'Liabilities:')) for item in cold)