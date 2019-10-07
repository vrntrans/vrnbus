from sqlalchemy import Column, String

from db import Base
from sqlalchemy import Column, String

from db import Base


class RouteEdges(Base):
    __tablename__ = 'route_edges'

    edge_key = Column(String(100), nullable=False, unique=True, index=True, primary_key=True)
    points = Column(String, nullable=False, default='')

    def __str__(self):
        return f"User({self.first_name} {self.last_name} | {self.email})"

