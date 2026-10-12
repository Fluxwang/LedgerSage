from datetime import date
from decimal import Decimal

from beanbot.services.agent.extract import ExtractedTransaction, extraction_issues, route_after_extract


def test_question_and_date_range_bounce_once_then_ask():
    issues = extraction_issues('我上个月为什么订阅花了150元', [])
    assert '含疑问词' in issues and '日期是范围' in issues
    assert route_after_extract(issues, 0) == 'classify'
    assert route_after_extract(issues, 1) == 'ask'


def test_extract_schema_accepts_a_three_transaction_batch():
    batch = [ExtractedTransaction(amount=Decimal(value), date=date(2026, 9, 9), payee=payee,
             from_account='Assets:Cash', to_account='Expenses:Other')
             for value, payee in [('12', '早餐店'), ('32', '出租车'), ('28', '咖啡店')]]
    assert len(batch) == 3