import ast
from pathlib import Path
import unittest


class NewGuildDayTests(unittest.TestCase):
    def test_today_completed_guild_does_not_reuse_old_battles(self):
        source = Path('tasks/GroupedAwakening/script_task.py').read_text(encoding='utf-8')
        function = next(node for node in ast.parse(source).body
                        if isinstance(node, ast.FunctionDef) and node.name == 'new_guild_batch')
        scope = {}
        exec(compile(ast.Module(body=[function], type_ignores=[]), '<new-guild-day>', 'exec'), scope)
        check = scope['new_guild_batch']
        old = dict(date='2026-11-17', updated_at='2026-11-18T19:41:24', status='运行中')
        guild = dict(date='2026-11-18', status='完成')
        self.assertTrue(check(old, guild, '2026-11-18'))
        self.assertFalse(check(dict(date='2026-11-18'), guild, '2026-11-18'))
        self.assertFalse(check(old, {}, '2026-11-18'))
        self.assertFalse(check(old, dict(date='2026-11-18', status='运行中'), '2026-11-18'))


if __name__ == '__main__':
    unittest.main()
