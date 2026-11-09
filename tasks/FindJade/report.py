"""Durable cooperation ledger and end-of-run WeChat summary."""
import csv
import io
import json
import re
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4


REWARDS = {'JADE': '勾玉', 'DOG_FOOD': '狗粮', 'CAT_FOOD': '猫粮',
           'SUSHI': '体力', 'GOLD': '金币'}


def current_period(now):
    if now.hour >= 18:
        return now.replace(hour=18, minute=0, second=0, microsecond=0)
    if now.hour >= 5:
        return now.replace(hour=5, minute=0, second=0, microsecond=0)
    return (now - timedelta(days=1)).replace(hour=18, minute=0, second=0, microsecond=0)


class CooperationReport:
    def __init__(self, config_name, root=Path('log/FindJade/reports')):
        now = datetime.now()
        self.period = current_period(now)
        self.config_name = config_name
        safe_name = re.sub(r'[^\w.-]', '_', config_name).strip('.') or 'config'
        self.directory = Path(root) / safe_name
        self.directory.mkdir(parents=True, exist_ok=True)
        self.run_id = now.strftime('%Y%m%d-%H%M%S-') + uuid4().hex[:8]
        self.ledger_path = self.directory / ('period-' + self.period.strftime('%Y%m%d-%H%M') + '.json')
        self.records = {}
        previous_accounts = []
        if self.ledger_path.exists():
            stored = json.loads(self.ledger_path.read_text(encoding='utf-8'))
            if stored.get('schema') != 1 or stored.get('period') != self.period.isoformat():
                raise ValueError('Unexpected cooperation report ledger format')
            self.records = stored.get('records', {})
            previous_accounts = stored.get('accounts', [])
        self.started_at = now.isoformat(timespec='seconds')
        self.finished_at = None
        self.accounts = {json.dumps([a['character'], a['server']], ensure_ascii=False): a
                         for a in previous_accounts}
        self.status = '运行中'
        self.notification = '尚未推送'
        self.flush()

    @staticmethod
    def account_key(account):
        return json.dumps([account.character, account.svr], ensure_ascii=False)

    @staticmethod
    def account_prefix(account):
        """Expose only the first four characters of email login names."""
        login = (getattr(account, 'account', '') or '').strip()
        local, separator, domain = login.partition('@')
        if separator and local and domain:
            return local[:4]
        return ''

    @staticmethod
    def account_label(record):
        prefix = record.get('account_prefix', '')
        return f'{record["character"]}（邮箱前四位：{prefix}）' if prefix else record['character']

    @staticmethod
    def category(item):
        kind = int(item['type'])
        reward = item.get('reward_kind')
        if kind == 16:
            return '现世协作', REWARDS.get(reward, '未知奖励')
        if kind == 2:
            return '勾协', '勾玉'
        if kind == 4:
            label = REWARDS.get(reward, '狗粮/猫粮')
            return label + '协作', label
        return None

    def account_status(self, account, status):
        prefix = self.account_prefix(account)
        self.accounts[self.account_key(account)] = {
            'character': account.character, 'server': account.svr, 'status': status,
            'account_prefix': prefix}
        # Previously observed rows from this refresh period may predate the
        # prefix field. Update them as soon as the account is registered.
        for row in self.records.values():
            if row['character'] == account.character and row['server'] == account.svr:
                row['account_prefix'] = prefix
        self.flush()

    def observe(self, account, items):
        # Never merge new-refresh quests into the previous period's ledger.
        if current_period(datetime.now()) != self.period:
            return
        counts = Counter()
        shared_counts = Counter()
        for item in items:
            category = self.category(item)
            if category:
                counts[category] += 1
                if item.get('already_shared'):
                    shared_counts[category] += 1
        for (category, reward), count in counts.items():
            key = json.dumps([account.character, account.svr, category, reward], ensure_ascii=False)
            row = self.records.setdefault(key, {
                'character': account.character, 'server': account.svr,
                'category': category, 'reward': reward, 'found_count': 0,
                'first_seen': datetime.now().isoformat(timespec='seconds'),
                'invitations': [], 'last_failure': ''})
            row['account_prefix'] = self.account_prefix(account)
            row['observed_shared_count'] = max(row.get('observed_shared_count', 0),
                                               shared_counts[(category, reward)])
            # Repeated scans of an unchanged board must not inflate its count.
            row['found_count'] = max(row['found_count'], count)
            row['last_seen'] = datetime.now().isoformat(timespec='seconds')
        self.flush()

    def invitation(self, account, item, recipient, success):
        category = self.category(item)
        if not category:
            return
        self.observe(account, [item])
        key = json.dumps([account.character, account.svr, *category], ensure_ascii=False)
        row = self.records.get(key)
        if row is None:
            return
        if success:
            row['invitations'].append({'recipient': recipient,
                                       'sent_at': datetime.now().isoformat(timespec='seconds'),
                                       'run_id': self.run_id, 'accepted': None,
                                         'send_confirmation': item.get('send_confirmation'),
                                       'sender_work_required': int(item['type']) != 16,
                                       'sender_tracked': False, 'sender_completed': False})
            row['last_failure'] = ''
        else:
            row['last_failure'] = item.get('skip_reason') or ('邀请失败或未选中好友：' + recipient)
        self.flush()

    def sender_pending(self, account):
        return [event for row in self.records.values()
                if row['character'] == account.character and row['server'] == account.svr
                for event in row['invitations']
                if event.get('sender_work_required') and not event.get('sender_completed')]

    def sender_traced(self, account, item, recipient):
        category = self.category(item)
        if category is None:
            return
        key = json.dumps([account.character, account.svr, *category], ensure_ascii=False)
        for event in reversed(self.records[key]['invitations']):
            if event['recipient'] == recipient and event['run_id'] == self.run_id:
                event['sender_tracked'] = True
                self.flush()
                return

    def sender_finished(self, account):
        for event in self.sender_pending(account):
            event['sender_completed'] = True
            event['sender_completed_at'] = datetime.now().isoformat(timespec='seconds')
        self.flush()

    @staticmethod
    def sender_state(row):
        work = [event for event in row['invitations'] if event.get('sender_work_required')]
        if not work:
            return '未记录' if row['invitations'] else '不适用'
        return f"已完成 {sum(bool(event.get('sender_completed')) for event in work)}/{len(work)}"

    def finish(self, status):
        self.status = status
        self.finished_at = datetime.now().isoformat(timespec='seconds')
        self.flush()

    @staticmethod
    def atomic_write(path, text, encoding='utf-8'):
        temporary = path.with_name(path.name + '.' + uuid4().hex + '.tmp')
        # csv.writer already emits CRLF; Windows text translation would turn
        # it into CRCRLF and insert an empty row after every CSV record.
        with temporary.open('w', encoding=encoding, newline='') as stream:
            stream.write(text)
        temporary.replace(path)

    def flush(self):
        for row in self.records.values():
            shared = max(len(row['invitations']), row.get('observed_shared_count', 0))
            row['surplus_count'] = max(0, row['found_count'] - shared)
        payload = {'schema': 1, 'config': self.config_name, 'period': self.period.isoformat(),
                   'run_id': self.run_id, 'started_at': self.started_at,
                   'finished_at': self.finished_at, 'status': self.status,
                   'notification': self.notification, 'accounts': list(self.accounts.values()),
                   'records': self.records}
        text = json.dumps(payload, ensure_ascii=False, indent=2)
        self.atomic_write(self.ledger_path, text)
        self.atomic_write(self.directory / (self.run_id + '.json'), text)
        self.atomic_write(self.directory / 'latest.json', text)
        stream = io.StringIO(newline='')
        writer = csv.writer(stream)
        writer.writerow(['小号角色', '邮箱前四位', '区服', '类别', '奖励', '发现数量', '已发邀请数', '界面已分享数',
                         '分享对象及时间', '接受状态', '最近失败或跳过原因', '多余数量', '小号任务完成状态'])
        for row in self.records.values():
            invitations = row['invitations']
            writer.writerow([row['character'], row.get('account_prefix', ''), row['server'], row['category'], row['reward'],
                             row['found_count'], len(invitations), row.get('observed_shared_count', 0),
                             '; '.join(event['recipient'] + ' ' + event['sent_at'] for event in invitations),
                             '未确认接受' if invitations else '未分享', row['last_failure'], row['surplus_count'], self.sender_state(row)])
        self.atomic_write(self.directory / (self.run_id + '.csv'), stream.getvalue(), 'utf-8-sig')
        self.atomic_write(self.directory / 'latest.csv', stream.getvalue(), 'utf-8-sig')

    def messages(self, limit=6000):
        rows = list(self.records.values())
        found = sum(row['found_count'] for row in rows)
        shared = sum(min(row['found_count'], max(len(row['invitations']), row.get('observed_shared_count', 0))) for row in rows)
        lines = [f'## {self.config_name} 协作任务汇总', f'本轮结果：{self.status}',
                 f'刷新时段：{self.period:%Y-%m-%d %H:%M} 起',
                 f'本时段累计发现 {found} 条，已分享 {shared} 条，多余未分享 {found - shared} 条。',
                 '分享状态指邀请已发出，不代表大号已接受。',
                 '现世协作仅记录，不自动邀请。',
                 '同小号、同类别和奖励的任务合并显示数量；重试沿用本时段记录。',
                 f'本轮小号状态：{len(self.accounts)} 个有处理记录。', '']
        for row in rows:
            invitations = row['invitations']
            sent = len(invitations)
            state = (f'已发 {sent} 条邀请 → ' + '、'.join(event['recipient'] for event in invitations)
                     if invitations else '多余未分享')
            observed = row.get('observed_shared_count', 0)
            if observed and not sent:
                state = f'界面显示已分享 {observed} 条（发送详情未记录）'
            remaining = row['found_count'] - max(sent, observed)
            if remaining > 0 and (sent or observed):
                state += f'；另有 {remaining} 条多余未分享'
            line = (f'- {self.account_label(row)}｜{row["server"]}｜{row["category"]} '
                    f'({row["reward"]}) ×{row["found_count"]}｜{state}')
            if row['last_failure']:
                line += '｜' + row['last_failure']
            if any(event.get('sender_work_required') for event in invitations):
                line += '｜小号部分：' + self.sender_state(row)
            lines.append(line)
        if not rows:
            lines.append('尚无已识别的勾协、狗粮/猫粮或现世任务。未扫描不等于没有任务。')
        for account in self.accounts.values():
            if account['status'] != '扫描完成':
                lines.append(f'- 小号状态：{self.account_label(account)}｜{account["server"]}｜{account["status"]}')
        lines.append('完整 JSON/CSV 已保存到本机：' + str(self.directory.resolve()))
        parts, current = [], ''
        for line in lines:
            if len((current + line + '\n').encode('utf-8')) > limit and current:
                parts.append(current)
                current = ''
            current += line + '\n'
        if current:
            parts.append(current)
        return parts
