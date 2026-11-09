"""Navigate the apprentice to the soul dungeon without starting a battle."""
from module.config.config import Config
from tasks.Mentorship.device import BoundDevice, validate_profiles
from tasks.Orochi.script_task import ScriptTask
from tasks.GameUi.page import page_soul_zones

mentor, apprentice = Config('oas1'), Config('oas_leveling')
validate_profiles(mentor, apprentice)
device = BoundDevice(apprentice)
task = ScriptTask(apprentice, device)
if not task.ui_goto_page(page_soul_zones, timeout=35):
    raise RuntimeError('未找到御魂入口')
if not task.orochi_enter():
    raise RuntimeError('未进入八岐大蛇')
if not task.check_layer('壹层'):
    raise RuntimeError('未找到御魂壹层')
print('OROCHI_LAYER_SELECTED', flush=True)
