from pydantic import Field

from tasks.Component.config_base import ConfigBase
from tasks.Component.config_scheduler import Scheduler


class EyeAwakeningOptions(ConfigBase):
    max_battles_per_account: int = Field(default=300, ge=1, le=1000,
                                         description='每个账号最多战斗次数，达到后停止并保留进度')


class EyeAwakening(ConfigBase):
    scheduler: Scheduler = Field(default_factory=Scheduler)
    options: EyeAwakeningOptions = Field(default_factory=EyeAwakeningOptions)
