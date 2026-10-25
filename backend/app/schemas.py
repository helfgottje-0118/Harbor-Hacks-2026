from datetime import datetime

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


class IncidentCreate(BaseModel):
    water_depth_cm: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    observed_at: AwareDatetime | None = None
    source: str = "WEB"
    node_id: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    category: str = "UNCLASSIFIED"
    description: str
    severity: str | None = None
    people_affected: int = 0
    status: str = "REPORTED"
    ai_reasoning: str | None = None
    recommended_action: str | None = None
    location: str | None = None


class IncidentRead(BaseModel):
    water_depth_cm: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    observed_at: AwareDatetime | None = None
    model_config = ConfigDict(from_attributes=True)

    id: int
    timestamp: datetime
    source: str
    node_id: str | None
    location: str | None = None
    latitude: float | None
    longitude: float | None
    category: str
    description: str
    severity: str
    people_affected: int
    status: str
    ai_reasoning: str | None
    recommended_action: str | None


class ResourceCreate(BaseModel):
    latitude: float | None = Field(default=None, ge=-90, le=90, allow_inf_nan=False)
    longitude: float | None = Field(default=None, ge=-180, le=180, allow_inf_nan=False)

    @model_validator(mode="after")
    def paired_coordinates(self):
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("latitude and longitude must be supplied together")
        return self

    name: str
    type: str
    status: str = "AVAILABLE"
    location: str | None = None
    capacity: int | None = None
    notes: str | None = None


class ResourceRead(ResourceCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int


class TaskCreate(BaseModel):
    incident_id: int | None = None
    title: str
    priority: str = "LOW"
    assigned_resource: str | None = None
    status: str = "OPEN"


class TaskRead(TaskCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime


class NodeCreate(BaseModel):
    node_name: str
    latitude: float | None = None
    longitude: float | None = None
    battery: int | None = None
    status: str = "ONLINE"


class NodeRead(NodeCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    last_seen: datetime | None


class MeshMessage(BaseModel):
    water_depth_cm: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    observed_at: AwareDatetime | None = None
    node: str
    type: str
    priority: str = "NORMAL"
    lat: float | None = None
    lon: float | None = None
    message: str


class PlanRequest(BaseModel):
    command: str = "HARBOR, make an action plan."
    constraint: str | None = None


class BriefingRequest(BaseModel):
    style: str = "30-second incident commander briefing"


class GeocodeResult(BaseModel):
    location: str
    latitude: float
    longitude: float
    display_name: str
    street_address: str
    provider: str
    maps_url: str

