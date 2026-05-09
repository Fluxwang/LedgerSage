from __future__ import annotations

import os
from pathlib import Path
import gettext as gettext_module

DOMAIN = "beanbot"
_proxied_gettext = gettext_module.gettext


def gettext(message):
    return _proxied_gettext(message)


def init_locale(settings):
    locale_dir = Path(__file__).resolve().parent.parent / "locale"
    global _proxied_gettext
    language = settings.get("language")
    if language is not None:
        translation = gettext_module.translation(
            DOMAIN, locale_dir, [language], fallback=True
        )
        _proxied_gettext = translation.gettext
    else:
        env_language = os.environ.get("LANG", "").split(".")[0] or None
        languages = [env_language] if env_language else None
        translation = gettext_module.translation(
            DOMAIN, locale_dir, languages=languages, fallback=True
        )
        _proxied_gettext = translation.gettext
