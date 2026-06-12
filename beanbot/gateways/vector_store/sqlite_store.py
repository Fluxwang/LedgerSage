from __future__ import annotations

from operator import itemgetter
from pathlib import Path
import sqlite3
import struct

import sqlite_vec

from beanbot.gateways.vector_store.base import calculate_score


def serialize_f32(vector: list[float]) -> bytes:
    """将vector的浮点数列表打包成二进制字符串
    struct.pack(format, v1, v2, ...)
    format: 格式字符串，告诉pack每个数字用什么二进制保存
    "768f" = 768个float32, 每个值都使用 float32去存储
    *列表: 把列表展开成独立参数
    """
    return struct.pack(f"{len(vector)}f", *vector)


class SqliteVectorStore:
    def __init__(self, settings) -> None:
        self.settings = settings
        self._db = None

    @property
    def db_path(self) -> Path:
        db_dir = self.settings.embedding.get("db_store_folder", ".")
        return Path(db_dir) / "tx_db.sqlite"

    def get_db(self):
        if self._db is not None:
            return self._db

        self._db = sqlite3.connect(self.db_path)
        self._db.enable_load_extension(True)
        # 便捷封装
        sqlite_vec.load(self._db)
        self._db.enable_load_extension(False)
        return self._db

    def build(self, transactions: list[dict]):
        """
        {
            # hash 的值为Beancount 自带的函数所生成
            "hash": "tx_kfc_20240501",
            "sentence": "KFC 午餐",
            "embedding": [1.0, 0.0, 0.0],
            "occurance": 8,
            "content": '2024-05-01 * "KFC" "午餐"\n  Assets:Bank:CMB  -35.00 CNY\n  Expenses:Food',
        },
        """
        db = self.get_db()
        # 设置embedding 维度
        embedding_dimension = 1
        if transactions:
            embedding_dimension = len(transactions[0]["embedding"])

        db.execute("DROP TABLE IF EXISTS vec_items")
        db.execute("DROP TABLE IF EXISTS transactions")
        db.commit()
        # VACUUM整理并压缩数据库文件
        db.execute("VACUUM")
        db.commit()

        db.execute(
            # 创建虚拟表, 使用vec0这个扩展搜索引擎，定义了名为embedding的列
            # 并且类型是固定长度的float 数组, 其长度为f-string 赋值
            f"CREATE VIRTUAL TABLE IF NOT EXISTS vec_items USING vec0(embedding float[{embedding_dimension}])"
        )
        # 创建 transactions表用于存放普通数据，与 vec_items 进行隔离
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS transactions (
            id integer primary key,
            hash varchar(64) unique,
            occurance integer,
            sentence text,
            content text)
            """
        )
        # sqlite 的 rowis 是 从1 开始的
        # 将index 和 embedding 数据存放在 vec_db 中
        for index, transaction in enumerate(transactions, 1):
            db.execute(
                "INSERT INTO vec_items (rowid, embedding) VALUES (?,?)",
                (index, serialize_f32(transaction["embedding"])),
            )
            db.execute(
                "INSERT INTO transactions (id, hash, occurance, sentence, content) VALUES (?, ?, ?, ?, ?)",
                (
                    index,
                    transaction["hash"],
                    transaction["occurance"],
                    transaction["sentence"],
                    transaction["content"],
                ),
            )
            db.commit()

    def query(
        self, embeding: list[float], sentence: str, candidate_amount: int
    ) -> list[dict]:
        """根据输入向量查找最相似的历史交易
        Args:
            embedding: 查询语句的 embedding 向量
            sentence: 原始自然语言查询语句，用于计算 score
            candidate_amount: 从向量库中取多少条候选结果

        Returns:
            按score 从高到低排序的交易列表，每条包含id, occurance, sentence, content, distance, score

        Example:
            input: ([0.1, 0.2, 0.3,...], "肯德基 午餐", 3)
            Returns: [{"sentence": "肯德基 午饭 CMB Food", "score":0.95, ...}]
        """
        db = self.get_db()
        try:
            # vec_distance_cosine(a,b)计算a和b向量之间的余弦距离，范围为[0, 2]，越接近0越相似
            # 1 - vec_distance_cosine 转为相似度，范围[-1, 1]，越接近1越相似
            rows = db.execute(
                f"""
                SELECT
                rowid,
                1-vec_distance_cosine(embedding, ?) AS similarity
                FROM vec_items
                ORDER BY similarity DESC LIMIT {candidate_amount}
                """,
                (serialize_f32(embeding),),
                # serialize_f32把Python的浮点数转化为二进制的字符串
                # fetchall 一次性全部取出，返回列表
            ).fetchall()
        except sqlite3.OperationalError as exc:
            if "no such table" in exc.args[0]:
                return []
            raise

        if not rows:
            return []

        # 只取出rowsid 的值，现在的ids 就是按照similarity从高到低进行排序的结果的rowid
        ids = [row[0] for row in rows]
        # []的作用就是把字符串变成列表，让 * 操作能生成独立的元素
        # ["?"] -> ["?", "?", "?"]
        # 然后 join 需要iterable才能将每个元素之间插入分隔符，之后返回 "?,?,?"
        # placeholder 为下面的SQL查询做准备
        placeholder = ",".join(["?"] * len(ids))
        row_names = ["id", "occurance", "sentence", "content"]
        rows_str = ", ".join(row_names)
        transaction_rows = db.execute(
            f"SELECT {rows_str} FROM transactions WHERE id in ({placeholder})",
            ids,
        ).fetchall()
        # ids.index 返回这个值在列表里的下标
        # 因为SQL的行为特性，WHERE id IN (...) 不保证返回顺序， 它可能按主键顺序返回
        # 所以要通过ids.index() 去判断 对应的 row[0] 就是rowid 在 ids 中的index
        # ids.index(5), 就是5 这个数在ids中的index，这样就还是按照ids的顺序进行排列
        transaction_rows.sort(key=lambda row: ids.index(row[0]))

        candidates = []
        # rows是向量表中的数据, 有similarity
        # transaction_rows是交易表中的数据, 有内容
        # zip 就是把两个列表的第0个配第0个, 第1个配第1个，变成一堆二元组
        for distance_row, transaction_rows in zip(rows, transaction_rows):
            tx_row = dict(zip(row_names, transaction_rows))
            # 获取 similarity
            tx_row["distance"] = distance_row[1]
            tx_row["score"] = calculate_score(tx_row, sentence)
            candidates.append(tx_row)

        candidates.sort(key=itemgetter("score"), reverse=True)
        return candidates


"""
目前cadidates 的数值
  [
      {
          "id": 5,
          "occurance": 8,
          "sentence": "买咖啡",
          "content": '2024-05-01 * "KFC" "午餐"\n  Assets:Bank:CMB  -35.00 CNY\n  Expenses:Food',
          "distance": 0.92,   # 相似度高
          "score": 1.12,      # 0.92 + log(8+1, 50) ≈ 0.92 + 0.13 * 8... 综合分最高
      },
      {
          "id": 2,
          "occurance": 50,
          "sentence": "超市购物",
          "content": '2024-04-10 * "超市" "日用品"\n  Assets:Bank:CMB  -120.00 CNY\n  Expenses:Shopping',
          "distance": 0.75,   # 相似度稍低
          "score": 0.98,      # 但出现频率高，综合分第二
      },
]
"""
