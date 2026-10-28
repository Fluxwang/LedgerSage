"""收支表：账户层级 × 连续多个月的发生额矩阵。"""
from datetime import date

from fastapi.testclient import TestClient

from beanbot.api.app import create_app
from beanbot.gateways.ledger import LedgerFactory
from beanbot.gateways.ledger.accounts import account_matches
from beanbot.gateways.ledger.statements import income_statement
from tests.test_api import settings
from tests.test_dashboard import register

# 9 月：餐饮 100、买菜 50、直接记在汇总账户 Expenses:Food 上的旧交易 20、交通 300，
#       餐饮退款 30、工资 8000、一笔美元餐饮；10 月：买菜 80、工资 8000。
LEDGER = '''
1970-01-01 open Expenses:Food
1970-01-01 open Expenses:Food:Groceries
  name: "买菜"
1970-01-01 open Assets:Bank:USD

2026-09-02 * "火锅店"
  Expenses:Food:Dining  100.00 CNY
  Assets:WeChat:Balance

2026-09-03 * "菜场"
  Expenses:Food:Groceries  50.00 CNY
  Assets:WeChat:Balance

2026-09-04 * "老账"
  Expenses:Food  20.00 CNY
  Assets:WeChat:Balance

2026-09-05 * "火车"
  Expenses:Transport  300.00 CNY
  Assets:WeChat:Balance

2026-09-06 * "火锅店" "退款"
  Expenses:Food:Dining  -30.00 CNY
  Assets:WeChat:Balance

2026-09-10 * "公司"
  Assets:DebitCard:A  8000.00 CNY
  Income:Salary

2026-09-12 * "海外"
  Expenses:Food:Dining  10.00 USD
  Assets:Bank:USD

2026-10-03 * "菜场"
  Expenses:Food:Groceries  80.00 CNY
  Assets:WeChat:Balance

2026-10-10 * "公司"
  Assets:DebitCard:A  8000.00 CNY
  Income:Salary
'''


def ledger_with(tmp_path, text=LEDGER):
    ledger = LedgerFactory(settings(tmp_path)).get({'id': 'one', 'ledger_path': None})
    (ledger.root / '2026').mkdir(exist_ok=True)
    (ledger.root / '2026/fixture.bean').write_text(text, encoding='utf-8')
    ledger.reload()
    assert not ledger.errors
    return ledger


def rows(statement):
    return {row['account']: row for row in statement['rows']}


def test_parent_rows_sum_descendants_including_direct_postings(tmp_path):
    statement = income_statement(ledger_with(tmp_path), date(2026, 9, 1), date(2026, 10, 31))
    table = rows(statement)
    assert [period['period'] for period in statement['periods']] == ['2026-09', '2026-10']
    assert table['Expenses:Food']['cells'] == ['140.00', '80.00']
    assert table['Expenses']['cells'] == ['440.00', '80.00']


def test_refunds_net_against_expenses_and_income_is_positive(tmp_path):
    table = rows(income_statement(ledger_with(tmp_path), date(2026, 9, 1), date(2026, 10, 31)))
    assert table['Expenses:Food:Dining']['cells'] == ['70.00', '0.00']
    assert table['Income']['cells'] == ['8000.00', '8000.00']
    assert table['Income:Salary']['cells'] == ['8000.00', '8000.00']


def test_tree_depth_and_display_names(tmp_path):
    table = rows(income_statement(ledger_with(tmp_path), date(2026, 9, 1), date(2026, 10, 31)))
    assert (table['Income']['display_name'], table['Expenses']['display_name']) == ('收入', '支出')
    # 开了户但没写 name: 的汇总账户退回最后一段；开户带 name: 的用中文名。
    assert table['Expenses:Food']['display_name'] == 'Food'
    assert table['Expenses:Food:Groceries']['display_name'] == '买菜'
    assert table['Expenses:Food:Dining']['display_name'] == '餐饮'
    assert [table[key]['depth'] for key in ('Expenses', 'Expenses:Food', 'Expenses:Food:Dining')] == [0, 1, 2]


def test_unopened_middle_level_still_appears(tmp_path):
    text = '''
1970-01-01 open Expenses:Home:Rent

2026-09-01 * "房东"
  Expenses:Home:Rent  3000.00 CNY
  Assets:DebitCard:A
'''
    table = rows(income_statement(ledger_with(tmp_path, text), date(2026, 9, 1), date(2026, 9, 30)))
    assert table['Expenses:Home']['display_name'] == 'Home'
    assert table['Expenses:Home']['cells'] == ['3000.00']


def test_zero_rows_dropped_and_siblings_sorted_by_total(tmp_path):
    statement = income_statement(ledger_with(tmp_path), date(2026, 9, 1), date(2026, 10, 31))
    accounts = [row['account'] for row in statement['rows']]
    assert 'Expenses:Other' not in accounts
    assert accounts == [
        'Income', 'Income:Salary',
        'Expenses', 'Expenses:Transport', 'Expenses:Food',
        'Expenses:Food:Groceries', 'Expenses:Food:Dining',
    ]


def test_roots_are_kept_even_when_empty(tmp_path):
    statement = income_statement(ledger_with(tmp_path, ''), date(2026, 9, 1), date(2026, 9, 30))
    assert statement['rows'] == [
        {'account': 'Income', 'display_name': '收入', 'depth': 0, 'cells': ['0.00']},
        {'account': 'Expenses', 'display_name': '支出', 'depth': 0, 'cells': ['0.00']},
    ]


def test_foreign_currency_is_skipped_and_reported(tmp_path):
    statement = income_statement(ledger_with(tmp_path), date(2026, 9, 1), date(2026, 10, 31))
    assert statement['currency'] == 'CNY'
    assert statement['skipped_currencies'] == ['USD']


def test_truncated_last_month_is_partial(tmp_path):
    statement = income_statement(ledger_with(tmp_path), date(2026, 9, 1), date(2026, 10, 27))
    assert statement['periods'] == [
        {'period': '2026-09', 'partial': False},
        {'period': '2026-10', 'partial': True, 'through': '2026-10-27'},
    ]


def test_matches_dashboard_category_totals(tmp_path):
    ledger = ledger_with(tmp_path)
    table = rows(income_statement(ledger, date(2026, 9, 1), date(2026, 9, 30)))
    totals = ledger.expense_totals(date(2026, 9, 1), date(2026, 9, 30))
    for row in table.values():
        if row['account'].startswith('Expenses'):
            expected = sum(amount for account, amount in totals.items()
                           if account_matches(account, row['account']))
            assert row['cells'] == [f'{expected:.2f}'], row['account']


def client_get(tmp_path, query):
    app = create_app(settings(tmp_path))
    with TestClient(app) as client:
        return client.get(f'/statements/income{query}', headers=register(client))


def test_default_range_is_last_six_months_with_current_partial(tmp_path):
    response = client_get(tmp_path, '')
    assert response.status_code == 200
    periods = response.json()['periods']
    today = date.today()
    assert len(periods) == 6
    assert periods[-1]['period'] == today.strftime('%Y-%m')
    assert periods[-1].get('through') == today.isoformat()
    assert all(not period['partial'] for period in periods[:-1])


def test_explicit_range(tmp_path):
    response = client_get(tmp_path, '?start=2025-11&end=2026-02')
    assert [period['period'] for period in response.json()['periods']] == [
        '2025-11', '2025-12', '2026-01', '2026-02',
    ]


def test_invalid_ranges_are_rejected(tmp_path):
    today = date.today()
    future = date(today.year + 1, today.month, 1).strftime('%Y-%m')
    app = create_app(settings(tmp_path))
    with TestClient(app) as client:
        headers = register(client)
        for query in ('?start=2026-9&end=2026-10', '?start=2026-10&end=2026-09',
                      '?start=2020-01&end=2022-01', f'?end={future}', '?start=2026-13'):
            assert client.get(f'/statements/income{query}', headers=headers).status_code == 422, query


def test_parent_kept_when_children_cancel_out(tmp_path):
    text = '''
1970-01-01 open Expenses:Home:Rent
1970-01-01 open Expenses:Home:Deposit

2026-09-01 * "房东"
  Expenses:Home:Rent  50.00 CNY
  Assets:DebitCard:A

2026-09-02 * "房东" "押金退回"
  Expenses:Home:Deposit  -50.00 CNY
  Assets:DebitCard:A
'''
    table = rows(income_statement(ledger_with(tmp_path, text), date(2026, 9, 1), date(2026, 9, 30)))
    assert table['Expenses:Home']['cells'] == ['0.00']
    assert table['Expenses:Home:Rent']['cells'] == ['50.00']
