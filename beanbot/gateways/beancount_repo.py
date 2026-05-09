from __future__ import annotations
from datetime import datetime
from decimal import Decimal
from pathlib import Path
import subprocess

from beancount.core.number import MISSING
from beancount.parser.printer import EntryPrinter
from beancount.parser import parser
from beanquery.query import run_query
from beancount import loader
from beancount.core.amount import Amount
from beancount.core import data as d


NO_TRANSACTION_ERROR = ValueError("No Transaction found")


class BeancountRepository:
    """账本数据访问层"""

    def __init__(self, filename: str | Path, currency: str, logger):
        self.filename = filename
        self.currency = currency
        self.logger = logger
        self._load()

    def _load(self):
        """加载账本文件"""
        self._entries, errors, self._options = loader.load_file(self.filename)
        self._accounts = set()
        self.mtimes = {}
        self.account_files = set()

        for error in errors:
            self.logger.warning("Beancount load error: %s", error)

        # 收集账户列表
        for entry in self._entries:
            if isinstance(entry, d.Open):
                self._accounts.add(entry.account)
                self.account_files.add(entry.meta["filename"])
            elif isinstance(entry, d.Close):
                self._accounts.remove(entry.account)
                self.account_files.remove(entry.meta["filename"])

        for include_file in self._options["include"]:
            # 获取文件最后修改时间
            self.mtimes[include_file] = Path(include_file).stat().st_mtime

        self._printer = EntryPrinter(dcontext=self._options.get("dcontext"))

    def _auto_reload(self, accounts_only: bool = False):
        """自动更新, 当设置accounts_only 将只检查account条目更新"""
        files_to_check = self.mtimes.keys()
        if accounts_only:
            files_to_check = self.account_files

        for filename in files_to_check:
            if self.mtimes[filename] != Path(filename).stat().st_mtime:
                self._load()
                return

    def find_account(
        self, account_fragment: str, range_: list[int] | None = None
    ) -> str | None:
        """根据账户片段查找完整账户名。
        Args:
            account_fragment: 要匹配的账户片段
            range_: 允许拿账户的第几层到第几层来做匹配, [2,3]类似与切片 Assets:Bank:Checking 就只取 Checking

        Returns:
            匹配到的完整账户名并且返回，如果没有就返回None

        input: Checking
        Returns: Assets:Bank:Checking
        """
        if range_ is None:
            range_ = [2, 4]

        candidates = []
        for account in self.accounts:
            parts = account.split(":")
            if len(parts) < range_[0]:
                continue

            for i in range(range_[0], min(range_[1] + 1, len(parts) + 1)):
                partial = ":".join(parts[:i])
                if partial.endswith(account_fragment):
                    # 添tuple 对象
                    candidates.append((i, account))
                    break
        if not candidates:
            return None

        candidates.sort(key=lambda x: x[0])
        return candidates[0][1]

    def find_account_by_payee(self, payee: str) -> str | None:
        """根据 payee 查找历史交易中最可能复用的对手账户。

        Args:
            payee: 收款方/商家名称

        Returns:
            找到则返回账户名字符串，找不到返回 None。
            优先返回最近一笔同 payee 交易中金额为 MISSING
            或 meta 中带 __automatic__ 的 posting.account；
            如果没有这种 posting，则返回该交易里第一个
            Expenses: 开头的账户作为兜底。

            支持省略 to_account: 根据历史同 payee 交易补全对
            手账户，优先取自动平衡(MISSING/__automatic__)
            否则回退到第一个 Expenses 账户
            (因为后面会设置to_account 全部为 MISSING)

            就可以直接输入 35 CMB KFC 午饭
            - 找不到账户 KFC
            - 就把它当成 payee
            - 再调用 find_account_by_payee("KFC")
            - 从历史交易里找到 Expenses:Food

            最后补全成类似：
            2026-04-23 * "KFC" "午饭"
                Assets:Bank:CMB    -35 CNY
                Expenses:Food
        """
        expense_account = None
        for entry in reversed(self.entries):
            if isinstance(entry, d.Transaction) and entry.payee == payee:
                for posting in entry.postings:
                    posting_meta = posting.meta or {}
                    if posting.units is MISSING or posting_meta.get("__automatic__"):
                        return posting.account
                    if (
                        posting.account.startswith("Expenses:")
                        and expense_account is None
                    ):
                        expense_account = posting.account
                return expense_account
        return None

    def build_transaction_entry(
        self,
        payee: str,
        narration: str,
        from_account: str,
        to_account: str,
        amount: Decimal,
        tags: set[str] | None = None,
        date: datetime | None = None,
    ) -> d.Transaction:
        # 创建一个新的元数据容器, <generated>对应filename参数，告诉系统这条数据是被生成的，并不存在于实际的物理账本目录中
        meta = d.new_metadata("<generated>", 0)
        postings = [
            d.Posting(
                account=from_account,
                units=Amount(amount, self.currency),
                cost=None,
                price=None,
                flag=None,
                meta=None,
            ),
            d.Posting(
                account=to_account,
                units=Amount(-amount, self.currency),
                # units=MISSING,
                cost=None,
                price=None,
                flag=None,
                meta=None,
            ),
        ]
        return d.Transaction(
            meta=meta,
            date=date.date() if date else datetime.now().date(),
            flag="*",
            payee=payee,
            narration=narration,
            tags=frozenset(tags) if tags else frozenset(),
            links=frozenset(),
            postings=postings,
        )

    def render_entry(self, entry) -> str:
        """将交易对象格式化为文本"""
        if not hasattr(self, "_printer"):
            # dcontext 是显示上下文，控制小数位数等格式
            self._printer = EntryPrinter(dcontext=self._options.get("dcontext"))
        return self._printer(entry)

    def parse_transactions(self, text: str):
        """解析交易
        Args:
            text: 传入文本参数
        Returns:
            (entries, errors, options)
        """
        return parser.parse_string(text)

    def run_query(self, query: str):
        """查询交易
        调用 beanquery.query.run_query 执行 BQL 查询交易

        Returns:
            返回查询结果
        """
        return run_query(self.entries, self.options, query)

    def clone_transaction(self, text: str, amount: Decimal | None = None) -> str:
        """根据模板交易文本克隆一条新交易，可选的金额
        Args:
            text: 模板交易文本，包括日期、payee、postings
            等完整交易信息

            amount: 可选, 如果传入则替换第一条非 MISSING 的
            posting 金额，也就是覆盖模板交易文本的 amount 部分

        Returns:
            渲染后的交易文本字符串

        """

        entries, _, _ = self.parse_transactions(text)
        try:
            # next() 的作用为 让这个迭代器开始执行，取第一个值出来
            transaction = next(
                entry for entry in entries if isinstance(entry, d.Transaction)
            )
        except StopIteration as exc:
            raise NO_TRANSACTION_ERROR from exc

        if amount is not None:
            # 使用 enumerate 进行编号遍历-- 一边遍历一边给每个元素贴个序号
            for index, posting in enumerate(transaction.postings):
                if posting.units is not MISSING:
                    transaction.postings[index] = d.Posting(
                        account=posting.account,
                        units=Amount(Decimal(-amount), self.currency),
                        meta=posting.meta,
                        cost=posting.cost,
                        price=posting.price,
                        flag=posting.flag,
                    )
                    break
        transaction = d.Transaction(
            date=datetime.now().astimezone().date(),
            flag=transaction.flag,
            payee=transaction.payee,
            narration=transaction.narration,
            meta=transaction.meta,
            postings=transaction.postings,
            tags=transaction.tags,
            links=transaction.links,
        )
        return self.render_entry(transaction)

    def append_transaction(self, data: str):
        """追加交易到账本文件。

        Args:
            data: 要追加到账本中的交易文本

        Raises:
          subprocess.CalledProcessError: bean-format
          格式化失败时抛出
        """
        path = Path(self.filename)
        prefix = "" if path.stat().st_size == 0 else "\n"

        # 追加新的交易内容
        with open(self.filename, "a", encoding="utf-8") as f:
            f.write(prefix + data.strip("\n") + "\n")

        # 格式化文件
        subprocess.run(
            ["bean-format", "-o", str(self.filename), str(self.filename)],
            check=True,
            shell=False,
        )
        # 重新加载
        self._load()

    @property
    def entries(self):
        self._auto_reload()
        return self._entries

    @property
    def options(self):
        self._auto_reload()
        return self._options

    @property
    def accounts(self):
        self._auto_reload(accounts_only=True)
        return self._accounts
