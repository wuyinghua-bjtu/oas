from dataclasses import dataclass
from datetime import date
from typing import Literal


@dataclass(frozen=True)
class MentorSettings:
    apprentice_name: str = 'OASPlayer004'
    apprentice_server: str = '砂狐乐园'
    mentor_profile: str = 'oas1'
    apprentice_profile: str = 'oas_leveling'

    def validate(self):
        if not self.apprentice_name.strip():
            raise ValueError('徒弟昵称不能为空')
        if self.mentor_profile == self.apprentice_profile:
            raise ValueError('师父和徒弟必须使用不同的设备配置')


@dataclass(frozen=True)
class Activity:
    name: Literal['guard', 'experience', 'gold', 'tako', 'apprentice_souls']
    rounds: int | None
    mentor_buffs: tuple[str, ...] = ()
    mentor_exit_after_prepare: bool = False


def daily_plan(day: date) -> tuple[Activity, ...]:
    activities = [Activity('guard', None),
                  Activity('experience', 2, ('exp_50', 'exp_100')),
                  Activity('gold', 2, ('gold_50', 'gold_100'))]
    if day.weekday() < 5:
        activities.append(Activity('tako', 2, mentor_exit_after_prepare=True))
    activities.append(Activity('apprentice_souls', 15))
    return tuple(activities)
