from app.db.base import Base
from app.db.session import engine
from app.db import models  # noqa: F401


if __name__ == '__main__':
    Base.metadata.create_all(bind=engine)
    print('DB schema created')
