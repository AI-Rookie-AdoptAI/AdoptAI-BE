from pydantic import BaseModel, Field


class ShelterResponse(BaseModel):
    id: str
    name: str
    region: str
    address: str | None = None
    phone: str
    email: str | None = None
    capacity: int | None = None
    description: str | None = None


class UpdateShelterRequest(BaseModel):
    name: str = Field(..., min_length=1)
    region: str = Field(..., min_length=1)
    phone: str = Field(..., min_length=1)
    address: str | None = None
    email: str | None = None
    capacity: int | None = None
    description: str | None = None
