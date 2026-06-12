from __future__ import annotations
from decimal import Decimal, InvalidOperation
from beancount.core.compare import hash_entry

from beancount.core import data as d
from beanbot.services.parser import parse_args


class VectorService:
    def __init__(self, settings, embedding_client, vector_store, rag_client, logger):
        self.settings = settings
        self.embedding_client = embedding_client
        self.vector_store = vector_store
        self.rag_client = rag_client
        self.logger = logger

    def convert_account(self, account: str) -> str:
        """分割账户名，去配置指定范围的段
        dist_range 既可以是 int 也可以是 序列([start, end])

        Args:
            account: 类似于 Expenses:Food:Lunch 或 Assets:DebitCard:HKD:ZA-1234

        Returns:
            segments 为 空列表时(切片越界导致结果为空): 返回你输入的原始 account
            segments 不为 空列表时: 返回根据你的 account_distinguation_range 的长度拆分的str

        """
        dist_range = self.settings.beancount.account_distinguation_range
        segments = account.split(":")
        if isinstance(dist_range, int):
            segments = segments[dist_range : dist_range + 1]
        else:
            segments = segments[dist_range[0] : dist_range[1] + 1]
        if not segments:
            return account
        return ":".join(segments)

    def escape_quotes(self, value: str | None):
        """将字符串中的双引号转义," -> \"
        为了防止出现条目中意外含有" 时，导致格式解析出错
        """
        if not value:
            return value
        return value.replace('"', '\\"')

    def convert_to_natural_language(self, transaction) -> str:
        """将一个 transaction 转换成一句自然语言描述(payee + narration + accounts + tags)
        Args:
            transaction: 传入的是beancount.core.data.Transaction 的 namedtuple 的实例
            具有.payee .narration .postings .tags 等字段属性可以直接访问

        Returns:
            "星巴克 冰美式 Assets:HKD:ZA-123 Expenses:Drink"
        """
        payee = f"{self.escape_quotes(transaction.payee)}"
        narration = f"{self.escape_quotes(transaction.narration)}"
        accounts = " ".join(
            [self.convert_account(posting.account) for posting in transaction.postings]
        )
        sentence = f"{payee} {narration} {accounts}"
        if transaction.tags:
            tags = " ".join(["#" + tag for tag in transaction.tags])
            sentence += f" {tags}"
        return sentence

    def build_transaction_db(self, transactions) -> int:
        """构建交易条目"""
        content_cache = {}

        def read_lines(filename, start, end):
            if filename not in content_cache:
                with open(filename, mode="r", encoding="utf-8") as file:
                    content_cache[filename] = file.readlines()
                    # 因为start_lineno 是从 1 开始的，而不是从0开始的, 所以这里的start要-1
            return content_cache[filename][start - 1 : end]

        # unique_transactions 的 key 为 sentence 的值, 目的是 同一条 sentence 以及存在就直接 occurance + 1
        unique_transactions = {}
        amount = int(self.settings.embedding.transaction_amount)
        for entry in reversed(transactions):
            if not isinstance(entry, d.Transaction):
                continue
            # sentence 已经通过 escape_quotes 函数完成自然语言转换
            sentence = self.convert_to_natural_language(entry)
            if sentence in unique_transactions:
                # 如果 sentence 已经在 unique_transactions 中存在直接 occurance + 1
                unique_transactions[sentence]["occurance"] += 1
                continue
            filename = entry.meta["filename"]
            start_lineno = entry.meta["lineno"]
            # end_lineno = max(posting.meta["lineno"] for posting in entry.postings)
            end_lineno = max(
                (
                    # 一个Transaciton 的 postings 有两条信息
                    posting.meta["lineno"]
                    for posting in entry.postings
                    if posting.meta is not None
                ),
                default=start_lineno,
            )

            unique_transactions[sentence] = {
                "sentence": sentence,
                "hash": hash_entry(entry),
                "occurance": 1,
                "content": "".join(read_lines(filename, start_lineno, end_lineno)),
            }
            # 最多不超过配置文件中设置的 amount
            if len(unique_transactions) >= amount:
                break
        total_usage = 0
        # 将values 用 list 进行表示
        unique_transactions_list = list(unique_transactions.values())
        for index in range(0, len(unique_transactions_list), 32):
            # 使用切片进行每批32个进行处理
            sentence_batch = [
                item["sentence"]
                for item in unique_transactions_list[index : index + 32]
            ]
            # 使用embed进行请求，返回的 embeddings 是 list[dict]
            embeddings, usage = self.embedding_client.embed(sentence_batch)
            # zip 将list 里的每个 dict 逐个取出来
            for item, embedding in zip(
                unique_transactions_list[index : index + 32], embeddings
            ):
                # 每次循环, embedding 只是其中一个 dict,
                item["embedding"] = embedding["embedding"]
            total_usage += usage

        self.vector_store.build(unique_transactions_list)
        self.logger.info("Total token usage: %d", total_usage)
        return total_usage

    def query_transactions(self, query: str) -> list[dict]:
        """根据用户输入查询最相似的历史交易
        candidates 表示先从向量库里找多少条候选结果
        output_amount 表示最终只返回前几条结果
        """
        candidates = self.settings.embedding.candidates or 3
        output_amount = self.settings.embedding.output_amount or 1
        # 因为 embedding client 的输入参数为 listp[str]， 所以这里也要为 [query]
        embeddings, _ = self.embedding_client.embed([query])
        matches = self.vector_store.query(embeddings[0]["embedding"], query, candidates)
        return matches[:output_amount]

    def modify_args_via_vector(self, args: list[str]) -> list[list[str]]:
        """进行向用户输入纠错
        Args:
            args: ["50", "招商银行", "肯德基", "午餐"]
        Returns: 多组候选参数
            [['50', 'Assets:Bank', 'Expenses:Food','肯德基', '午餐', '#lunch']]
        """
        #
        matched_transactions = self.query_transactions(" ".join(args[1:]))
        candidate_args = []
        for transaction in matched_transactions:
            sentence = parse_args(transaction["sentence"])
            tags = [segment for segment in sentence[4:] if segment.startswith("#")]
            # sentence = f"{payee} {narration} {accounts}"
            # [2:4] 为历史交易中的两个账户, sentence[:2] 取出历史交易中的 payee 和 narration
            # [金额, from_account, to_account, payee, narration, tag1, tag2, ...]
            new_args = [args[0]] + sentence[2:4] + sentence[:2] + tags
            candidate_args.append(new_args)
        return candidate_args

    def complete_with_rag(self, args: list[str], date: str, accounts: list[str]) -> str:
        try:
            Decimal(args[0])
            stripped_input = " ".join(args[1:])
        except InvalidOperation:
            stripped_input = " ".join(args[0:])

        candidates = self.settings.embedding.candidates or 3
        embeddings, _ = self.embedding_client.embed([stripped_input])
        matches = self.vector_store.query(
            embeddings[0]["embedding"], stripped_input, candidates
        )
        reference_records = [match["content"] for match in matches]
        return self.rag_client.complete_transaction(
            args, date, accounts, reference_records
        )
