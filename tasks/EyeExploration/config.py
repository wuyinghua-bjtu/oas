from pydantic import Field
from tasks.Component.config_base import ConfigBase
from tasks.Component.config_scheduler import Scheduler
from tasks.Exploration.config import ExplorationLevel


class EyeExplorationOptions(ConfigBase):
    exploration_level: ExplorationLevel = Field(default=ExplorationLevel.EXPLORATION_28,
                                                description='探索章节')
    max_battles: int = Field(default=500, ge=1, le=2000, description='单次运行最多战斗场数')


class EyeExploration(ConfigBase):
    scheduler: Scheduler = Field(default_factory=Scheduler)
    options: EyeExplorationOptions = Field(default_factory=EyeExplorationOptions)
