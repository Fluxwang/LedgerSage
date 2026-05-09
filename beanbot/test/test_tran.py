from beanbot.settings import Settings

from beanbot.i18n import init_locale, gettext as _

# 测试中文翻译
settings = Settings.from_dict({"language": "zh_CN"})
init_locale(settings)
print(_("Account {acc} not found").format(acc="Assets:Bank"))

# 测试英文（默认）
settings = Settings.from_dict({})
init_locale(settings)
print(_("Account {acc} not found").format(acc="Assets:Bank"))
