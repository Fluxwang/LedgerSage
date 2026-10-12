"""运行：python -m tests.eval.classify。需要完整 .env。"""
import asyncio
from beanbot.config import Settings
from beanbot.services.agent.model import OpenAIAgentModel


CASES = [
    ('打车32', 'record'), ('星巴克38 微信', 'record'), ('午饭25', 'record'),
    ('昨天超市买菜86支付宝', 'record'), ('房租3500招行', 'record'), ('咖啡和蛋糕共45', 'record'),
    ('早饭12 打车32 咖啡28', 'record'), ('收到工资12000', 'record'),
    ('我上个月为什么订阅花了150元', 'query'), ('上次那顿火锅是不是花了128', 'query'),
    ('这个月餐饮超过500了吗', 'query'), ('上个月交通花了多少', 'query'), ('今年一共存了多少钱', 'query'),
    ('最近一笔咖啡是哪天', 'query'), ('微信余额是多少', 'query'), ('列出本周所有支出', 'query'),
    ('去年比今年花得多吗', 'query'), ('火锅店那笔走的什么账户', 'query'),
    ('给餐饮设个每月2000的预算', 'budget'), ('交通预算改成500', 'budget'),
    ('本月购物预算1000', 'budget'), ('取消餐饮预算', 'budget'), ('预算还剩多少', 'query'),
    ('你好', 'other'), ('帮帮我', 'other'), ('今天天气不错', 'other'),
    ('早饭12，对了这个月餐饮多少钱', 'other'), ('记一笔然后查余额', 'other'),
    ('嗯', 'other'), ('这是什么意思', 'other'),
]


async def main():
    model = OpenAIAgentModel(Settings())  # type: ignore[call-arg]
    correct = 0
    for text, expected in CASES:
        result = await model.classify(text, [])
        ok = result.intent == expected
        correct += ok
        print(('✓' if ok else '✗'), expected, '->', result.intent, text)
    print(f'准确率：{correct}/{len(CASES)} = {correct/len(CASES):.1%}')


if __name__ == '__main__':
    asyncio.run(main())