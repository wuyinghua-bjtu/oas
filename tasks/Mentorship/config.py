from pydantic import Field
from module.config.local_values import local_text
from tasks.Component.config_base import ConfigBase
from tasks.Component.config_scheduler import Scheduler


class MentorshipConfig(ConfigBase):
    mentor_profile: str = Field(default='oas1', description='mentorship_mentor_profile_help')
    apprentice_profile: str = Field(default='oas_leveling', description='mentorship_apprentice_profile_help')
    apprentice_name: str = Field(default=local_text('LOCAL_SUPPORT_004'), description='mentorship_apprentice_name_help')
    apprentice_server: str = Field(default='砂狐乐园', description='mentorship_apprentice_server_help')


class Mentorship(ConfigBase):
    scheduler: Scheduler = Field(default_factory=Scheduler)
    mentorship_config: MentorshipConfig = Field(default_factory=MentorshipConfig)
