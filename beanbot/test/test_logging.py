from beanbot.settings import load_settings
from beanbot.logging_config import init_logging

settings = load_settings("config.yaml")
logger = init_logging(settings)


logger.debug("这条 DEBUG 不会显示")
logger.info("这条 INFO 会显示")
logger.warning("这条 WARNING 会显示")

print(f"账本文件: {settings.beancount.filename}")
print(f"货币: {settings.beancount.currency}")
print(f"平台: {settings.bot.platform}")
