from __future__ import annotations

from pathlib import Path

import yaml

_IMMUTABLE_ERROR = TypeError("This directory is immutable")


class ImmutableDict(dict):
    # d["name"] = "mark"
    def __setitem__(self, key, value):
        del key, value
        raise _IMMUTABLE_ERROR

    # del d["name"]
    def __delitem__(self, key):
        del key
        raise _IMMUTABLE_ERROR

    def __setattr__(self, key, value):
        del key, value
        raise TypeError("ImmutableDict does not support attribute assignment")

    def __delattr__(self, key):
        del key
        raise TypeError("ImmutableDict does not support attribute deletion")

    # d.update({"a":1, "b":2})
    def update(self, *args, **kwargs):
        # *args 接收任意数量的位置参数
        # **kwargs 接收任意数量的关键字参数
        del args, kwargs
        raise _IMMUTABLE_ERROR

    # d.clear() 清理整个字典
    def clear(self):
        raise _IMMUTABLE_ERROR

    def pop(self, *args):
        del args
        raise _IMMUTABLE_ERROR

    def popitem(self):
        raise _IMMUTABLE_ERROR

    def setdefault(self, *args):
        del args
        raise _IMMUTABLE_ERROR


class Settings:
    # 读取配置文件，并把内容保存成字典，还可以是 Path对象Path('config.yaml')
    def __init__(self, config_path: str | Path):
        with open(config_path, "r", encoding="utf-8") as file:
            self._config = ImmutableDict(yaml.safe_load(file) or {})

    # 当需要判断 self._config 里面是否有内容
    def __bool__(self):
        return bool(self._config)

    # 从没有就返回 None, 修改为没有就返回 default
    def get(self, key, default=None):
        return self._config.get(key, default)

    # 到字典中查找
    def __setattr__(self, key, value):
        if key == "_config":
            # 只允许内部初始化
            super().__setattr__(key, value)
        else:
            raise _IMMUTABLE_ERROR

    # 当访问一个对象属性，但这个属性正常找不到时，Python 才会调用它
    def __getattr__(self, key):
        if key in self._config:
            value = self._config[key]
            if isinstance(value, dict):
                return self.__class__.from_dict(value)
            return value
        return self.__class__.from_dict({})

    @classmethod
    # classmethod 装饰类会自动接收类作为第一个参数
    # 等价于 settings = Settings.__new__(Settings)
    # 把这个字典套上 Settings 外壳，这样就能用点号访问了
    def from_dict(cls, dictionary):
        settings = cls.__new__(cls)
        settings._config = ImmutableDict(dictionary)
        return settings


def load_settings(config_path: str | Path) -> Settings:
    return Settings(config_path)
