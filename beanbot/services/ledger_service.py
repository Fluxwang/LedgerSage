from decimal import Decimal

from beanbot.i18n import gettext as _
from beanbot.services.parser import parse_args


class LedgerService:
    def __init__(self, settings, repository, vector_service):
        self.settings = settings
        self.repository = repository
        self.vector_service = vector_service

    @property
    def entries(self):
        return self.repository.entries

    def build_transaction(self, args: list[str]) -> str:
        """根据用户输入参数生成一条 Beancount 交易。

        Args:
            args: 已解析的参数列表，至少包含金额、付款
            账户和收款账户/商户。
                示例：["35", "CMB", "KFC", "午饭","#food"]。

        Returns:
            格式化后的交易文本。

        Raises:
            ValueError: 找不到付款账户、收款账户，或无
            法根据商户推断账户时抛出。
        """
        amount, from_acc, to_acc, *extra = args

        amount = Decimal(amount)
        from_account = self.repository.find_account(
            from_acc, self.settings.beancount.account_distinguation_range
        )
        to_account = self.repository.find_account(
            to_acc, self.settings.beancount.account_distinguation_range
        )
        payee = None

        if from_account is None:
            raise ValueError(_("Account {acc} not found").format(acc=from_acc))

        if to_account is None:
            payee = to_acc
            to_account = self.repository.find_account_by_payee(payee)
            if to_account is None:
                raise ValueError(_("Account {acc} not found").format(acc=to_acc))

        if payee is None:
            payee, *extra = extra

        description = ""
        tags = []
        for arg in extra:
            if arg.startswith(("#", "^")):
                # 去掉 # 或 ^ 在进行写入
                tags.append(arg[1:])
            elif not description:
                description = arg
        transaction = self.repository.build_transaction_entry(
            amount=amount,
            from_account=from_account,
            to_account=to_account,
            payee=payee,
            narration=description,
            tags=tags,
        )
        return "\n" + self.repository.render_entry(transaction)

    def generate_transactions(self, line: str) -> list[str]:
        args = parse_args(line)
        try:
            return [self.build_transaction(args)]
        except ValueError as original_error:
            raise original_error

    def clone_transaction(self, text: str, amount=None) -> str:
        return self.repository.clone_transaction(text, amount)

    def commit_transaction(self, data: str):
        self.repository.append_transaction(data)

    def clone_transaction_with_error(self, text: str, amount=None) -> str:
        try:
            return self.clone_transaction(text, amount)
        except ValueError as exc:
            # 假如我的 exc = ValueError("No Transaction found")的话
            # 我的 err.args 就是 ("No Transaction found",)
            # 所以 err.args[] 就是 No Transaction found
            # 因为 NO_TRANSACTION_ERROR 是 Repository层的内部错误
            # 不应该暴露给上层
            raise ValueError(exc.args[0]) from exc
