from pydantic import Field
from tasks.Component.config_base import ConfigBase, MultiLine
from tasks.Component.config_scheduler import Scheduler
from tasks.GuildQuickParticipation.policy import SERVER, SUPPORT_CHARACTERS


class GuildAccounts(ConfigBase):
    server: str = Field(default=SERVER, description='guild_accounts_server_help')
    characters: MultiLine = Field(default='\n'.join(SUPPORT_CHARACTERS), description='guild_accounts_characters_help')


class GuildQuickParticipation(ConfigBase):
    # Scheduler settings are controlled independently from FindJade.
    scheduler: Scheduler = Field(default_factory=Scheduler)
    guild_accounts: GuildAccounts = Field(default_factory=GuildAccounts)
