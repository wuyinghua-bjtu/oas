from pydantic import Field
from tasks.Component.config_base import ConfigBase
from tasks.Component.config_scheduler import Scheduler


class GroupedOptions(ConfigBase):
    credit_previous: bool = Field(default=False, description='首组计入此前已核实完成的15场')


class GroupedAwakening(ConfigBase):
    scheduler: Scheduler = Field(default_factory=Scheduler)
    options: GroupedOptions = Field(default_factory=GroupedOptions)
