# -*- coding: utf-8 -*-
"""黄瓜平台智能体真实评测：真实 LLM(deepseek-flash, Anthropic 协议) 跑 /eval/run 并留证。
运行：cucumber-agent/.venv/Scripts/python.exe tools/acceptance/cucumber_eval_run.py
前置：cucumber-agent(8002) 在跑且 ANTHROPIC_API_KEY 有效。
"""
import json, time, pathlib
import httpx

AGENT = "http://127.0.0.1:8002"
OUT = pathlib.Path(__file__).parent.parent.parent / "cucumber-diagnosis-platform" / "docs"
OUT.mkdir(parents=True, exist_ok=True)

intent_cases = [
    # disease_diagnosis
    {"message": "我上传了一张黄瓜叶片照片，帮我看看是什么病", "expected_intent": "disease_diagnosis"},
    {"message": "叶子上出现黄斑和霉层，这到底是什么病", "expected_intent": "disease_diagnosis"},
    {"message": "刚拍的这张图，帮我诊断一下叶片有没有问题", "expected_intent": "disease_diagnosis"},
    # prevention_qa
    {"message": "霜霉病一般怎么防治", "expected_intent": "prevention_qa"},
    {"message": "炭疽病在什么温湿度条件下容易发病", "expected_intent": "prevention_qa"},
    {"message": "棚里湿度大是不是容易长白粉病，怎么预防", "expected_intent": "prevention_qa"},
    # medication_advice
    {"message": "白粉病可以打什么药", "expected_intent": "medication_advice"},
    {"message": "醚菌酯喷完几天能采收", "expected_intent": "medication_advice"},
    {"message": "蔓枯病用咪鲜胺安全吗，间隔期多久", "expected_intent": "medication_advice"},
    # human_handoff
    {"message": "这个诊断结果我不认可，给我转人工专家", "expected_intent": "human_handoff"},
    {"message": "情况很严重可能绝收，我要人工复核", "expected_intent": "human_handoff"},
    # greeting
    {"message": "你好", "expected_intent": "greeting"},
    {"message": "早上好", "expected_intent": "greeting"},
    # other
    {"message": "今天天气怎么样", "expected_intent": "other"},
    {"message": "给我讲个笑话吧", "expected_intent": "other"},
]

dialog_cases = [
    {"question": "霜霉病怎么治？请结合知识库说明，并注明来源"},
    {"question": "炭疽病用什么药？用药上要注意什么安全问题"},
    {"question": "我家黄瓜叶子有白粉层，这是什么病，怎么治"},
]

print(f"评测用例：意图 {len(intent_cases)} 条 + 对话 {len(dialog_cases)} 条（真实 LLM，预计 3-8 分钟）")
t0 = time.time()
r = httpx.post(f"{AGENT}/eval/run", json={"intent_cases": intent_cases, "dialog_cases": dialog_cases},
               timeout=900, trust_env=False)
dt = time.time() - t0
d = r.json()
(OUT / "eval_run_20260914.json").write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")

print(f"HTTP {r.status_code} | 用时 {dt:.0f}s")
print(f"pass_rate={d.get('pass_rate')} | total={d.get('total')} passed={d.get('passed')}")
print(f"avg_scores={json.dumps(d.get('avg_scores'), ensure_ascii=False)}")
print(f"regressions={json.dumps(d.get('regressions'), ensure_ascii=False)[:200]}")
print(f"recommendations={json.dumps(d.get('recommendations'), ensure_ascii=False)[:200]}")
