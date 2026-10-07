"""LLM「语义验收官」适配层（OpenAI 兼容 chat/completions，tool-use）。

定位：** advisory 解释层，不覆盖确定性验收**。它吃进已经算好的结构化确定性证据
（checks/指标），通过 tool-use 要求模型输出 verdict + rationale + 引用的 check id，
随后把模型结论与确定性证据对齐——不一致就夹回到确定性结论并标注，严禁凭空编造。

配置全部来自环境变量（也可由调用方注入 config 用于测试）：
    LLM_BASE_URL   例如 https://api.openai.com/v1   （OpenAI 兼容）
    LLM_API_KEY    Bearer key；缺省则优雅降级
    LLM_MODEL      例如 gpt-4o-mini

无 key / 调用失败 / 输出无法解析时，自动回退到确定性规则结论，并在结果上明确标注
「确定性回退 / LLM 未配置」。测试与构建不依赖任何 key，也不联网（注入假 opener）。
"""
from __future__ import annotations
import json
import os
from urllib.request import Request, build_opener, HTTPRedirectHandler

from .observations import APIError, canonical

TOOL = {
    'type': 'function',
    'function': {
        'name': 'record_semantic_review',
        'description': '把对确定性探测证据的语义验收结论记录下来。只能引用给定证据中的检查项，禁止证据之外的推测；有未通过检查必须 rejected，全通过才可 accepted，证据矛盾/不足时 uncertain。',
        'parameters': {
            'type': 'object',
            'properties': {
                'verdict': {'type': 'string', 'enum': ['accepted', 'rejected', 'uncertain'], 'description': '依据证据给出的整体结论'},
                'rationale': {'type': 'string', 'description': '一句中文理由，必须引用具体观测值'},
                'cited_check_ids': {'type': 'array', 'items': {'type': 'string'}, 'description': '本结论引用的检查项 id'},
            },
            'required': ['verdict', 'rationale', 'cited_check_ids'],
            'additionalProperties': False,
        },
    },
}


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):  # pragma: no cover - 防御
        raise RuntimeError('LLM 接口不允许重定向')


def config_from_env():
    return {
        'base_url': os.environ.get('LLM_BASE_URL', '').rstrip('/'),
        'api_key': os.environ.get('LLM_API_KEY', ''),
        'model': os.environ.get('LLM_MODEL', ''),
    }


def _known(checks):
    return {c['id'] for c in checks}


def _summary(checks):
    return [{'id': c['id'], 'label': c['label'], 'passed': c['passed'], 'observed': c['observed'], 'requirement': c['requirement']} for c in checks]


def rule_fallback(checks, provider_name):
    failed = [c for c in checks if not c['passed']]
    if not failed:
        verdict = 'accepted'
        rationale = f'{provider_name}：{len(checks)} 项确定性检查全部通过（可用性/链身份/时效/回执覆盖/关联/耗时），证据支持交付。'
        cited = [c['id'] for c in checks]
    else:
        verdict = 'rejected'
        rationale = f'{provider_name}：{len(failed)} 项检查未通过——' + '；'.join(f'{c["label"]}＝「{c["observed"]}」' for c in failed) + '。证据不支持交付，应拒收并切换。'
        cited = [c['id'] for c in failed]
    return {
        'schema': 'jiangcheng-trust/semantic-review/1',
        'source': 'rule_fallback',
        'configured': False,
        'model': None,
        'verdict': verdict,
        'rationale': rationale,
        'cited_check_ids': cited,
        'grounded': True,
        'note': 'LLM 未配置（缺少 LLM_BASE_URL / LLM_API_KEY / LLM_MODEL），使用确定性规则回退结论。',
    }


def review_evidence(checks, provider_name='该服务', *, config=None, opener=None, timeout=20):
    if not isinstance(checks, list) or not checks:
        raise APIError('语义验收需要非空的 checks 证据')
    deterministic = 'accepted' if all(c['passed'] for c in checks) else 'rejected'
    cfg = config or config_from_env()
    if not cfg.get('api_key') or not cfg.get('base_url') or not cfg.get('model'):
        out = rule_fallback(checks, provider_name)
        out['deterministic_verdict'] = deterministic
        return out

    system = ('你是 Agent 服务的「语义验收官」。只能依据给定的确定性探测证据下结论，'
              '禁止证据之外的推测。证据里只要存在未通过检查，结论必须为 rejected；'
              '全部通过才可 accepted；证据矛盾或不足时 uncertain。')
    user = '请依据以下证据调用 record_semantic_review：\n' + canonical({'provider': provider_name, 'checks': _summary(checks)})
    body = {
        'model': cfg['model'],
        'messages': [{'role': 'system', 'content': system}, {'role': 'user', 'content': user}],
        'tools': [TOOL],
        'tool_choice': {'type': 'function', 'function': {'name': 'record_semantic_review'}},
        'temperature': 0,
    }
    request = Request(
        cfg['base_url'] + '/chat/completions',
        data=canonical(body).encode('utf-8'),
        headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + cfg['api_key'], 'User-Agent': 'JiangchengTrust/1.0'},
        method='POST',
    )
    try:
        with (opener or build_opener(NoRedirect)).open(request, timeout=timeout) as response:
            raw = response.read(256 * 1024 + 1)
        obj = json.loads(raw)
        message = obj['choices'][0]['message']
        call = message['tool_calls'][0]['function']['arguments']
        args = json.loads(call) if isinstance(call, str) else call
        verdict = args['verdict']
        if verdict not in ('accepted', 'rejected', 'uncertain'):
            raise ValueError('verdict')
        rationale = str(args['rationale'])
        cited = [str(x) for x in args.get('cited_check_ids', [])]
        known = _known(checks)
        cited = [c for c in cited if c in known]
        grounded = verdict == deterministic
        if not grounded:
            verdict = deterministic  # 结论以证据为准，LLM 不得推翻
            note = 'LLM 结论与确定性证据不一致，已以确定性验收为准（防凭空编造）。'
        else:
            note = 'LLM 结论与确定性证据一致。'
        return {
            'schema': 'jiangcheng-trust/semantic-review/1',
            'source': 'llm',
            'configured': True,
            'model': cfg['model'],
            'verdict': verdict,
            'rationale': rationale,
            'cited_check_ids': cited or [c['id'] for c in checks],
            'grounded': grounded,
            'note': note,
            'deterministic_verdict': deterministic,
        }
    except Exception as exc:  # 网络/解析/结构异常一律回退，不影响主流程
        out = rule_fallback(checks, provider_name)
        out['note'] = f'调用 OpenAI 兼容接口失败（{type(exc).__name__}），已确定性回退。'
        out['deterministic_verdict'] = deterministic
        return out
