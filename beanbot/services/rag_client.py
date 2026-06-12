import json

import requests

from beanbot.gateways.embedding_client import TIMEOUT

_PROMPT_TEMPLATE = """The user is using Beancount for bookkeeping. For simplicity, there is currently a set of accounting grammar that is converted by a program into complete transaction records. The format of the grammar is `<price> <outflow_account> [<inflow_account>] <payee> [<description>] [#<tag1> [#<tag2>] ...]`, where the inflow and outflow accounts are subject to fuzzy matching.

For example：`5 微信 餐饮 麦当劳 午饭 #tag1 #another` will be converted to the following record:

2024-08-16 * "麦当劳" "午饭" #tag1 #another
  Assets:Checking:微信支付:Deposit            -5.00 CNY
  Expenses:Daily:餐饮

However, user input is not accurate enough and may be missing some information, maybe it's payee or description, or one or all of accounts.  
I will provide you with several reference sets, hoping that you can combine the reference information with the user's input to piece together a complete accounting record.  
The user's input will be given by user.

You can do it as following:
1. Try your best to find the correct place for every given word from the reference sets, but not the accounting grammar.  
2. If any information is missing, you should take the information from the reference sets and try to fill the missing part.  
3. Only output the complete accounting record, without any quotes or delemeters.

Finally, there are some reference information.
Today's date: {date}
Reference account names are: `{accounts}`
Reference records are separated by dash delimiter:
{reference_records}
"""


class RagClient:
    def __init__(self, settings):
        self.settings = settings

    def complete_transaction(
        self,
        args: list[str],
        date: str,
        accounts: list[str],
        reference_records: list[str],
    ) -> str:
        """
        Args:
            args: 用户原始输入参数
            date: 今天的日期
            accounts: 已经确认存在的参考账户名
            reference_records: 相似历史交易的原始文本
        Returns:
            模型补全后的交易字符串
        """
        rag_client = self.settings.rag
        prompt = _PROMPT_TEMPLATE.format(
            date=date,
            reference_records="\n------\n".join(reference_records),
            accounts=accounts,
        )
        payload = json.dumps(
            {
                "model": rag_client.model,
                "stream": False,
                "messages": [
                    {"role": "system", "content": prompt},
                    {
                        "role": "user",
                        "content": " ".join(args),
                    },
                ],
            }
        )
        headers = {
            "Authorization": f"Bearer {rag_client.api_key}",
            "content-type": "application/json",
        }
        response = requests.post(
            rag_client.api_url, payload, headers=headers, timeout=TIMEOUT
        )
        response.raise_for_status()
        data = response.json()
        if "choices" in data:
            content = data["choices"][0]["message"]["content"]
        else:
            content = data["message"]["content"]
        return content.strip(" `\n")
