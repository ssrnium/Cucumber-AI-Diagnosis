# -*- coding: utf-8 -*-
"""D1 浏览器级主链路验收：黄瓜平台 13 步核心链路。
运行：tools/pw-venv/Scripts/python.exe tools/acceptance/d1_main.py
前置：admin(8080)/ai(8000)/agent(8002)/web(5173)/PG/Redis 全部在跑。
"""
import json, subprocess, sys, time, pathlib
from playwright.sync_api import sync_playwright

BASE = "http://localhost:5173"
API = "http://127.0.0.1:8080"
SHOTS = pathlib.Path(__file__).parent.parent / "logs" / "shots"
SHOTS.mkdir(parents=True, exist_ok=True)
IMG = pathlib.Path(__file__).parent.parent.parent / "cucumber-diagnosis-platform" / "test-assets" / "leaf-anthracnose-01.jpg"

RESULTS = []
def check(name, cond, extra=""):
    RESULTS.append((name, bool(cond), extra))
    print(f'{"✓" if cond else "✗"} {name} {extra}', flush=True)

def shot(page, name):
    p = SHOTS / f"{name}.png"
    try:
        page.screenshot(path=str(p), full_page=False)
    except Exception:
        pass

def psql(sql):
    r = subprocess.run([r"<user-home>\pgsql16\bin\psql.exe", "-U", "postgres", "-h", "127.0.0.1",
                        "-d", "cucumber_db", "-tAc", sql], capture_output=True, text=True, timeout=30)
    return r.stdout.strip()

def login(page, u, p):
    page.goto(BASE + "/login", wait_until="networkidle")
    page.fill('input[placeholder="用户名"]', u)
    page.fill('input[placeholder="密码"]', p)
    page.click(".login-btn")
    page.wait_for_url("**/dashboard", timeout=15000)

def logout(page):
    page.goto(BASE + "/login", wait_until="networkidle")
    page.evaluate("localStorage.clear()")
    page.goto(BASE + "/login", wait_until="networkidle")

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    ctx = browser.new_context(viewport={"width": 1500, "height": 900}, locale="zh-CN")
    page = ctx.new_page()

    # 1. 未登录访问受保护页 → 重定向登录页
    page.goto(BASE + "/diagnosis/upload", wait_until="networkidle")
    check("1 未登录访问受保护页重定向 /login", page.url.startswith(BASE + "/login"), page.url)

    # 2. 错误密码 → 错误提示
    page.fill('input[placeholder="用户名"]', "user")
    page.fill('input[placeholder="密码"]', "wrongpass")
    page.click(".login-btn")
    time.sleep(1.5)
    msg = page.locator(".el-message")
    check("2 错误密码提示", msg.count() > 0 and msg.first.is_visible(), msg.first.inner_text()[:40] if msg.count() else "无 toast")

    # 3. 正常登录 → 进入主界面
    login(page, "user", "User@123")
    page.wait_for_selector(".el-menu", timeout=10000)
    check("3 登录成功进入主界面", "/dashboard" in page.url, page.url)
    shot(page, "03-dashboard")

    # 4-8. 上传 → 诊断 → 病斑框/报告/来源
    page.goto(BASE + "/diagnosis/upload", wait_until="networkidle")
    page.set_input_files('input[type="file"]', str(IMG))
    time.sleep(0.8)
    before_total = int(psql("SELECT count(*) FROM diagnosis_record") or 0)
    with page.expect_response(lambda r: "/api/v1/diagnosis" in r.url and r.request.method == "POST", timeout=90000) as resp_info:
        page.click('.action-bar button:has-text("开始诊断")')
    resp = resp_info.value
    body = resp.json()
    rec = body.get("data") or {}
    rec_no = rec.get("record_no")
    check("4 上传并创建诊断任务（API 200）", resp.status == 200 and body.get("code") == 200, f"record_no={rec_no}")
    page.wait_for_selector(".detect-box", timeout=30000)
    boxes = page.locator(".detect-box").count()
    check("5 页面展示病斑框", boxes >= 1, f"框数={boxes}")
    page.wait_for_selector(".report-card", timeout=15000)
    card = page.locator(".report-card").inner_text()
    check("6 报告五段展示", all(k in card for k in ["诊断依据", "农艺措施", "化学防治", "安全注意", "来源追溯"]), "")
    check("7 类别与置信度展示", ("置信度" in card) and bool(rec.get("report", {}).get("disease_type")), f"conclusion={rec.get('report',{}).get('disease_type')}")
    shot(page, "07-diagnosis-result")

    # 8. 来源追溯弹窗
    page.locator(".source-tag").first.click()
    page.wait_for_selector(".el-dialog", timeout=10000)
    try:
        page.wait_for_function("() => (document.querySelector('.el-dialog')?.innerText || '').includes('KB-')", timeout=10000)
    except Exception:
        pass
    dlg = page.locator(".el-dialog").inner_text()
    check("8 来源追溯弹窗有原文", len(dlg) > 20 and ("KB-" in dlg), dlg[:50].replace("\n", " "))
    page.keyboard.press("Escape")
    shot(page, "08-source-dialog")

    # 9. 接口/页面/数据库一致性（计数受去重窗口影响只作参考，一致性以记录内容为准）
    after_total = int(psql("SELECT count(*) FROM diagnosis_record") or 0)
    db_row = psql(f"SELECT status || '|' || coalesce(model_version,'') || '|' || image_url FROM diagnosis_record WHERE record_no='{rec_no}'")
    check("9 数据库记录一致", db_row.startswith("DONE") and "/files/" in db_row,
          f"db={db_row} count={before_total}→{after_total}")

    # 10. 历史记录页查询 + 详情
    page.goto(BASE + "/diagnosis/records", wait_until="networkidle")
    page.wait_for_selector(".el-table__row", timeout=10000)
    row = page.locator(".el-table__row", has_text=rec_no)
    check("10 历史记录含新记录", row.count() == 1, f"rec_no={rec_no}")
    row.locator('button:has-text("详情")').click()
    page.wait_for_selector(".el-drawer", timeout=10000)
    drawer = page.locator(".el-drawer").inner_text()
    check("10b 详情抽屉展示结论与来源", "诊断结论" in drawer and "来源追溯" in drawer, "")
    shot(page, "10-record-detail")
    page.keyboard.press("Escape"); time.sleep(0.6)

    # 11. 提交用户反馈
    row = page.locator(".el-table__row", has_text=rec_no)
    row.locator('button:has-text("诊断有误")').click()
    page.wait_for_selector(".el-dialog", timeout=10000)
    page.locator(".el-dialog .el-select").click()
    time.sleep(0.5)
    page.locator(".el-select-dropdown__item", has_text="炭疽病").first.click()
    page.fill('.el-dialog textarea', "叶片症状更像炭疽病（验收测试反馈）")
    page.locator('.el-dialog button:has-text("提交")').click()
    time.sleep(1.5)
    fb = psql(f"SELECT verdict || '|' || review_status FROM diagnosis_feedback ORDER BY id DESC LIMIT 1")
    check("11 反馈提交并落库 PENDING", fb.startswith("WRONG|PENDING"), f"db={fb}")
    shot(page, "11-feedback")

    # 12. 专家复核（换 expert 登录）
    logout(page)
    login(page, "expert", "Expert@123")
    page.goto(BASE + "/diagnosis/review", wait_until="networkidle")
    page.wait_for_selector(".el-table__row", timeout=10000)
    frow = page.locator(".el-table__row").first
    frow.locator('button:has-text("复核处理")').click()
    page.wait_for_selector(".el-message-box", timeout=8000)
    page.locator(".el-message-box__btns .el-button--primary").click()
    time.sleep(1.5)
    fb2 = psql(f"SELECT review_status || '|' || coalesce(reviewer_id::text,'') FROM diagnosis_feedback ORDER BY id DESC LIMIT 1")
    check("12 专家复核流转 REVIEWED", fb2.startswith("REVIEWED"), f"db={fb2}")
    shot(page, "12-review")

    # 13. 操作日志（浏览器内用 admin 上下文调接口验证，页面版列后续）
    logout(page)
    login(page, "admin", "Admin@123")
    token = page.evaluate("localStorage.getItem('token')")
    log_data = page.evaluate("""async (t) => {
        const r = await fetch('/api/v1/system/log?page=1&size=5', {headers: {Authorization: 'Bearer ' + t}});
        return r.json();
    }""", token)
    log_list = (log_data.get("data") or {}).get("list") or []
    check("13 操作日志可查（浏览器上下文）", log_data.get("code") == 200 and len(log_list) > 0,
          f"total={(log_data.get('data') or {}).get('total')} 最新={log_list[0].get('operation') if log_list else None}")

    # 14. 智能体追问（农技诊断 Agent）
    logout(page)
    login(page, "user", "User@123")
    page.goto(BASE + "/agent/chat", wait_until="networkidle")
    page.fill(".chat-input textarea", "黄瓜霜霉病怎么防治？请结合知识库回答")
    page.click('.chat-input button:has-text("发送")')
    page.wait_for_selector(".msg-assistant .msg-meta", timeout=180000)
    meta_text = page.locator(".msg-assistant .msg-meta").last.inner_text()
    bubble = page.locator(".msg-assistant .msg-text").last.inner_text()
    check("14 智能体回复+意图/角色徽标", ("意图" in meta_text and "Agent" in meta_text and len(bubble) > 20),
          meta_text.replace("\n", " ")[:80])
    shot(page, "14-agent-chat")
    # 工具轨迹抽屉
    page.locator('.msg-assistant .msg-meta a, .msg-assistant .msg-meta .el-link').last.click()
    time.sleep(2)
    tr = page.locator(".el-drawer")
    check("14b 工具轨迹抽屉", tr.count() > 0 and tr.is_visible() and len(tr.inner_text()) > 10, "")
    shot(page, "14b-agent-trace")
    agent_msgs = psql("SELECT count(*) FROM agent_message")
    check("14c 智能体对话落审计库", int(agent_msgs or 0) > 0, f"agent_message 行数={agent_msgs}")

    browser.close()

fails = [r for r in RESULTS if not r[1]]
print(f"\n==== D1 汇总：{len(RESULTS) - len(fails)}/{len(RESULTS)} 通过 ====")
for n, c, e in fails:
    print(f"未过项: {n} {e}")
sys.exit(1 if fails else 0)
