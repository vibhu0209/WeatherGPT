from datetime import datetime, timezone
from typing import Literal
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='../.env', extra='ignore')
    openweather_api_key: str = ''
    weatherapi_key: str = ''
    imd_enabled: bool = False
    cap_alert_url: str = ''
    gemini_api_key: str = ''
    gemini_model: str = ''
    bhashini_compute_url: str = ''
    bhashini_api_key: str = ''
    bhashini_user_id: str = ''
    bhashini_translation_service_id: str = ''
    google_translate_api_key: str = ''

class Location(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    timezone: str = 'Asia/Kolkata'
    @field_validator('timezone')
    @classmethod
    def valid_zone(cls, value):
        try: ZoneInfo(value)
        except Exception: raise ValueError('Unknown timezone')
        return value

class Point(BaseModel):
    time: datetime
    temperature: float | None = Field(default=None, ge=-90, le=65)
    rain_chance: float | None = Field(default=None, ge=0, le=100)
    rain_mm: float | None = Field(default=None, ge=0, le=2000)
    wind_ms: float | None = Field(default=None, ge=0, le=150)
    humidity: float | None = Field(default=None, ge=0, le=100)
    apparent_temperature: float | None = Field(default=None, ge=-100, le=80)
    wind_direction: float | None = Field(default=None, ge=0, le=360)
    wind_gust_ms: float | None = Field(default=None, ge=0, le=180)
    visibility_m: float | None = Field(default=None, ge=0, le=500000)
    pressure_hpa: float | None = Field(default=None, ge=800, le=1100)
    cloud_cover: float | None = Field(default=None, ge=0, le=100)
    uv_index: float | None = Field(default=None, ge=0, le=30)
    weather_code: int | None = Field(default=None, ge=0, le=999)
    @field_validator('time')
    @classmethod
    def aware(cls, v):
        if v.tzinfo is None: raise ValueError('Timestamp must include timezone')
        return v.astimezone(timezone.utc)

class Forecast(BaseModel):
    provider: str
    model_family: str
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    hourly: list[Point]

class ChatRequest(BaseModel):
    text: str = Field(min_length=1, max_length=1000)
    location: Location
    language: Literal['en','hi','bn','te','mr','ta','gu','kn','ml','pa','or'] = 'en'
    profile: str = Field(default='general', max_length=40)
    day_offset: int = Field(default=0, ge=0, le=6)
    conversation_id: UUID = Field(default_factory=uuid4)
