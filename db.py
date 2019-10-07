import logging
import os
from contextlib import contextmanager
from datetime import datetime

from sqlalchemy import create_engine, Column, DateTime
# from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.ext.declarative import as_declarative
from sqlalchemy.orm import sessionmaker

logger = logging.getLogger("db")
try:
    import settings

    DB_LINK = settings.DB_LINK
except ImportError:
    env = os.environ
    DB_LINK = env.get('DB_LINK')

engine = create_engine(DB_LINK)


def add_row(entity):
    session = Session()
    session.add(entity)
    session.commit()


@as_declarative()
class Base:
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, index=True)


    def __repr__(self):
        return str(self)

    def __str__(self):
        return f'{self.__class__.__name__} {self.created_at} {self.updated_at}'

Session = sessionmaker(bind=engine)


@contextmanager
def session_scope(scope_info=None):
    """Provide a transactional scope around a series of operations."""
    session = Session()
    from sqlalchemy.orm.exc import NoResultFound
    try:
        yield session
        session.commit()
    except NoResultFound:
        logger.exception(scope_info)
        session.rollback()
    except Exception as ex:
        logger.exception(scope_info)
        session.rollback()
        raise
    finally:
        session.close()