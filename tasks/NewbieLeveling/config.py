"""Configuration for the isolated, deterministic small-account workflow."""

from pydantic import BaseModel, Field

from tasks.Component.config_base import ConfigBase
from tasks.Component.config_scheduler import Scheduler


class LevelingConfig(BaseModel):
    target_level: int = Field(default=30, ge=1, le=30)
    expected_serial: str = Field(default='127.0.0.1:16416')
    expected_handle: str = Field(default='MuMu安卓设备-1')
    expected_vm: str = Field(default='MuMuPlayer-15.0-1')
    # Optional manually pinned character label. A displayed name is not a
    # globally unique account ID; it is checked together with the instance.
    character_id: str = Field(default='')
    session_minutes: int = Field(default=20, ge=1, le=120)
    stamina_budget: int = Field(default=60, ge=0, le=500)
    unknown_timeout_seconds: int = Field(default=30, ge=5, le=120)
    action_interval_seconds: float = Field(default=2.0, ge=1.0, le=30.0)
    observe_only: bool = Field(default=True)
    level_confirmations: int = Field(default=2, ge=2, le=5)


class NewbieLeveling(ConfigBase):
    scheduler: Scheduler = Field(default_factory=Scheduler)
    leveling_config: LevelingConfig = Field(default_factory=LevelingConfig)
