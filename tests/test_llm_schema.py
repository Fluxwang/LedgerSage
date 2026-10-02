"""发给 LLM 的结构化输出 schema 必须是服务商能吃下的。"""
from datetime import date
import json
import re

import pytest

from beanbot.services.agent.classify import Classification
from beanbot.services.agent.model import BudgetPlan, ExtractBatch, OpenAIAgentModel, QueryPlan


SCHEMAS = [Classification, ExtractBatch, QueryPlan, BudgetPlan]
# 先行/后行断言：结构化输出的 schema 校验器普遍不支持，会直接 400。
LOOKAROUND = re.compile(r'\(\?[=!<]')


@pytest.mark.parametrize('model', SCHEMAS, ids=lambda model: model.__name__)
def test_schema_has_no_regex_lookaround(model):
    for pattern in re.findall(r'"pattern":\s*"((?:[^"\\]|\\.)*)"', json.dumps(model.model_json_schema())):
        assert not LOOKAROUND.search(pattern), f'{model.__name__} 的 pattern 含 lookaround：{pattern}'


def test_amount_is_declared_as_a_string_and_still_parses_exactly():
    """金额声明成字符串，既避开 Decimal 自带的正则，也不经过 float。"""
    amount = ExtractBatch.model_json_schema()['$defs']['ExtractedTransaction']['properties']['amount']
    assert amount['type'] == 'string'
    batch = ExtractBatch.model_validate({'transactions': [{
        'amount': '128.50', 'date': '2026-09-09', 'payee': '火锅店',
    }]})
    assert str(batch.transactions[0].amount) == '128.50'
    assert BudgetPlan.model_validate({'amount': '2000.00'}).amount is not None


def test_tags_schema_avoids_unique_items_and_values_are_still_deduplicated():
    transaction = ExtractBatch.model_json_schema()['$defs']['ExtractedTransaction']
    tags = transaction['properties']['tags']
    assert tags['type'] == 'array'
    assert 'uniqueItems' not in tags

    batch = ExtractBatch.model_validate({'transactions': [{
        'amount': '12.00',
        'date': '2026-09-17',
        'payee': '早餐店',
        'tags': ['早餐', '报销', '早餐'],
    }]})
    assert batch.transactions[0].tags == ['早餐', '报销']


def test_non_positive_amounts_are_still_rejected():
    with pytest.raises(ValueError):
        ExtractBatch.model_validate({'transactions': [{
            'amount': '-5', 'date': '2026-09-09', 'payee': '火锅店',
        }]})


async def test_extract_resolves_yesterday_against_the_supplied_current_date():
    class Runnable:
        async def ainvoke(self, prompt):
            transaction_date = '2026-09-16' if '今天是 2026-09-17' in prompt else '2026-09-03'
            return {'transactions': [{
                'amount': '6', 'date': transaction_date, 'payee': '地铁',
                'from_account': 'Assets:DebitCard:CN:Bank-01',
                'to_account': 'Expenses:Transport:Mass-transit',
            }]}

    class Chat:
        def with_structured_output(self, schema):
            return Runnable()

    model = OpenAIAgentModel.__new__(OpenAIAgentModel)
    model.chat = Chat()

    batch = await model.extract('昨天的地铁6块', [], [], today=date(2026, 9, 17))

    assert batch.transactions[0].date == date(2026, 9, 16)