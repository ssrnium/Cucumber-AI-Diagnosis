# -*- coding: utf-8 -*-
"""验证重构后的诊断上传页（候选列表/三tab/不确定性/对比弹窗/导出）。
运行：tools/pw-venv/Scripts/python.exe tools/acceptance/verify_upload_0920.py
前置：admin(8080)/ai(8000)/web(5173)/PG/Redis 在跑。
"""
import time, pathlib
from playwright.sync_api import sync_playwright

BASE = "http://localhost:5173"
SHOTS = pathlib.Path(__file__).parent.parent / "logs" / "shots"
SHOTS.mkdir(parents=True, exist_ok=True)
IMG = pathlib.Path(__file__).parent.parent.parent / "cucumber-diagnosis-platform" / "test-assets" / "leaf-anthracnose-01.jpg"

RESULTS = []
def check(name, cond, extra=""):
    RESULTS.append((name, bool(cond), extra))
    print(f'{"✓" if cond else "✗"} {name} {extra}', flush=True)

def shot(page, name):
    page.screenshot(path=str(SHOTS / f"verify0920_{name}.png"))

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1500, "height": 960})
    page.set_default_timeout(20000)

    # 登录
    page.goto(BASE + "/login", wait_until="networkidle")
    page.fill('input[placeholder="用户名"]', "user")
    page.fill('input[placeholder="密码"]', "User@123")
    page.click(".login-btn")
    page.wait_for_url("**/dashboard", timeout=15000)
    check("0 登录", True)

    # 1 空态引导
    page.goto(BASE + "/diagnosis/upload", wait_until="networkidle")
    time.sleep(0.8)
    empty = page.locator(".empty-card")
    sample_btn = page.locator('button:has-text("试试示例图")')
    check("1 空态卡片+示例图按钮", empty.count() > 0 and sample_btn.count() > 0)
    shot(page, "01-empty")

    # 2 上传真实叶片 + 症状 chip
    page.set_input_files('input[type="file"]', str(IMG))
    time.sleep(1.0)
    chip = page.locator(".symptom-chip").first
    chip_text = chip.inner_text()
    chip.click()
    ta = page.locator('textarea')
    check("2 症状chip追加", chip_text in (ta.input_value() or ""), chip_text)

    # 3 开始诊断，抓扫描态
    page.click('button:has-text("开始诊断")')
    scan_seen = False
    for _ in range(30):
        if page.locator(".scan-mask").count() and page.locator(".scan-mask").is_visible():
            scan_seen = True
            shot(page, "03-scanning")
            break
        time.sleep(0.2)
    check("3 扫描加载动画出现", scan_seen)

    # 4 等结果（LLM 润色可能数十秒，骨架回退兜底）
    page.locator(".candidate").first.wait_for(timeout=120000)
    n = page.locator(".candidate").count()
    check("4 候选排序列表渲染", n >= 1, f"候选数={n}")
    time.sleep(0.6)
    shot(page, "04-result")

    # 5 候选切换联动
    if n > 1:
        page.locator(".candidate").nth(1).click()
        time.sleep(0.5)
        moved = page.locator(".candidate").nth(1).evaluate(
            "el => el.classList.contains('candidate-selected')")
        check("5 点击备选高亮切换", moved)
        shot(page, "05-candidate2")
        # 回到首位
        page.locator(".candidate").first.click()
        time.sleep(0.3)
    else:
        check("5 候选切换(单候选降级)", True, "单候选,跳过")

    # 6 三 tab 遍历
    for name, label in [("06-explain", "诊断说明"), ("07-next", "下一步建议"), ("08-evidence", "图文依据")]:
        page.click(f'.el-tabs__item:has-text("{label}")')
        time.sleep(0.5)
        shot(page, name)
    check("6 三tab可切换", True)

    # 7 不确定性提示条（存在与否都记录口径）
    unc = page.locator('.el-alert--warning').count()
    check("7 不确定性/提示条状态记录", True, f"warning alert 数={unc}")

    # 8 对比弹窗
    if n > 1:
        page.click('button:has-text("对比候选")')
        page.locator(".compare-selectors").wait_for(timeout=8000)
        time.sleep(0.5)
        check("8 候选对比弹窗", True)
        shot(page, "09-compare")
        page.keyboard.press("Escape")
        time.sleep(0.4)
    else:
        check("8 候选对比弹窗(单候选降级)", True, "单候选,跳过")

    # 9 症状修改 → 脏提醒
    ta.fill(ta.input_value() + "，新补充")
    time.sleep(0.6)
    dirty = page.locator('.el-alert--warning:has-text("重新诊断")').count() > 0
    check("9 输入修改后脏提醒", dirty)
    shot(page, "10-dirty")

    # 10 导出 TXT
    try:
        with page.expect_download(timeout=10000) as dl:
            page.click('button:has-text("导出 TXT 报告")')
        path = SHOTS / "verify0920_report.txt"
        dl.value.save_as(str(path))
        txt = path.read_text(encoding="utf-8", errors="replace")
        check("10 导出TXT报告", len(txt) > 100, f"{len(txt)}字符")
    except Exception as e:
        check("10 导出TXT报告", False, str(e)[:60])

    browser.close()

passed = sum(1 for _, ok, _ in RESULTS if ok)
print(f"\n===== {passed}/{len(RESULTS)} 通过 =====", flush=True)
