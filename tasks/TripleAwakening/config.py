from pydantic import Field
from tasks.Component.config_base import ConfigBase
from tasks.Component.config_scheduler import Scheduler


class TripleAwakening(ConfigBase):
    # One controller owns all three windows. Do not enable three EvoZone workers.
    scheduler: Scheduler = Field(default_factory=Scheduler)
