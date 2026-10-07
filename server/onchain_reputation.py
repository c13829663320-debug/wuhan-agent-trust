"""链上信誉登记适配层（ERC-8004 风格，本地打桩）。

本模块把一次本实例观测映射成一条 ERC-8004 风格的信誉事件，并在「无链」时
写入本地 JSONL 打桩文件。项目本身**不上链、不持有私钥**；这里只定义清晰的
字段映射与对接边界，供另一个 Escrow/合约项目消费。

对接真实 EVM 合约时，把 StubReputationLedger.record 替换为一次合约调用，例如：

    ReputationRegistry(provider_id, score_delta, evidence_hash, evidence_uri)
    - provider_id   : bytes32 服务商标识（这里先链下字符串，部署时改 bytes32）
    - score_delta   : int256，验收通过 +1 / 拒收 -1
    - evidence_hash : bytes32 = 观测 receipt_hash（SHA-256，与链下重放一致）
    - evidence_uri  : string，证据包取址（本地 local:// 或上传后的 HTTPS URI）
    - submitted_by  : msg.sender（独立验证者，本项目无签名身份，先留空）

安全边界：绝不在此保存私钥/助记词；合约调用应由外部带签名的中继完成。
"""
from __future__ import annotations
import json
import threading
from pathlib import Path

from .observations import canonical

SCHEMA = 'erc8004-style/reputation-event/1'
LEDGER_SCHEMA = 'erc8004-style/reputation-ledger/1'


def build_reputation_event(observation):
    """把一条验收观测映射为 ERC-8004 风格信誉记录。失败时抛错由调用方处理。"""
    provider = observation['provider']
    failed = [c['id'] for c in observation['checks'] if not c['passed']]
    accepted = bool(observation['accepted'])
    return {
        'schema': SCHEMA,
        'provider_id': provider['id'],
        'provider_name': provider.get('name'),
        'service_endpoint': provider.get('url'),
        'score_delta': 1 if accepted else -1,
        'evidence_hash': observation['receipt_hash'],
        'evidence_uri': 'local://observations/' + observation['receipt_hash'],
        'contract_id': observation['contract']['id'],
        'rule_version': observation['contract']['version'],
        'decision': observation['decision'],
        'failed_check_ids': failed,
        'injected': bool(observation.get('injected', False)),
        'issued_at': observation['issued_at'],
        'onchain': False,
        'note': '本地打桩：未上链、无签名身份；对接 EVM 合约见 server/onchain_reputation.py 与 README。',
    }


class StubReputationLedger:
    """无链打桩账本：以 JSONL 追加信誉事件，权限 0600。"""

    def __init__(self, data_dir):
        root = Path(data_dir)
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = root / 'reputation-events.jsonl'
        self.lock = threading.RLock()
        if not self.path.exists():
            self.path.touch(mode=0o600)
        self.path.chmod(0o600)

    def record(self, event):
        line = canonical(event)
        with self.lock:
            with self.path.open('a', encoding='utf-8') as handle:
                handle.write(line + '\n')
        return event

    def records(self):
        with self.lock:
            lines = self.path.read_text(encoding='utf-8').splitlines()
        events = [json.loads(x) for x in lines if x.strip()][-100:]
        events.reverse()
        summary = {}
        for event in reversed(events):
            bucket = summary.setdefault(event['provider_id'], {'provider_id': event['provider_id'], 'provider_name': event['provider_name'], 'score': 0, 'events': 0})
            bucket['score'] += event['score_delta']
            bucket['events'] += 1
        return {
            'schema': LEDGER_SCHEMA,
            'onchain': False,
            'note': '本地打桩信誉账本；不是链上注册、不抗女巫、不代表全网共识。对接 EVM 见 README。',
            'events': events,
            'scoreboard': list(summary.values()),
        }
