from datetime import date
from decimal import Decimal
import pytest

from beanbot.services.agent.confidence import account_confidence
from beanbot.services.agent.extract import extraction_issues, route_after_extract
from beanbot.services.agent.query import DateRange, normalize_period
from beanbot.services.agent.classify import Classification, route_classification


def test_extract_bounces_a_question_with_a_date_range():
    issues = extraction_issues('我上个月为什么订阅花了150元', [])
    assert '含疑问词' in issues
    assert '日期是范围' in issues
    assert route_after_extract(issues, bounce_count=0) == 'classify'
    assert route_after_extract(issues, bounce_count=1) == 'ask'


def test_history_frequency_is_explainable():
    history = [('火锅', 'Assets:WeChat:Balance')] * 6 + [('火锅', 'Liabilities:CreditCard')] * 2
    evidence = account_confidence('火锅', history)
    assert evidence[0].ratio == Decimal('0.75')
    assert evidence[0].label == 'Assets:WeChat:Balance 6/8'
    assert account_confidence('新商户', history) == []


def test_last_month_crosses_year_boundary():
    assert normalize_period('last_month', date(2026, 1, 5)) == DateRange(
        start=date(2025, 12, 1), end=date(2025, 12, 31)
    )


@pytest.mark.parametrize(('intent', 'confidence', 'route'), [
    ('record', .9, 'record'), ('query', .9, 'query'), ('budget', .9, 'budget'),
    ('other', .9, 'ask'), ('record', .5, 'ask'),
])
def test_classification_routes(intent, confidence, route):
    assert route_classification(Classification(intent=intent, confidence=confidence)) == route