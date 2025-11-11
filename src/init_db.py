from .db import engine, Base
from . import models  # noqa: F401  # 테이블 로딩

if __name__ == "__main__":
    Base.metadata.create_all(engine)
    print("[OK] SQLite tables created.")