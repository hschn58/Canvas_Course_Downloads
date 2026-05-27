from pydantic import BaseModel


class Course(BaseModel):
    id: str
    name: str
    url: str
