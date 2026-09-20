# -*- coding: utf-8 -*-
"""黄瓜平台演示视频录制（Playwright recordVideo → webm）。
运行：tools/pw-venv/Scripts/python.exe cucumber-diagnosis-platform/acceptance/cucumber_demo_record.py
前置：admin(8080)/ai(8000)/agent(8002)/web(5173)/PG/Redis 在跑。
"""
import time, pathlib
from playwright.sync_api import sync_playwright

BASE = "http://localhost:5173"
OUT = pathlib.Path(__file__).parent.parent.parent / "tmp_extract" / "cucumber_demo_raw"
OUT.mkdir(parents=True, exist_ok=True)
IMG = pathlib.Path(__file__).parent.parent / "test-assets" / "leaf-anthracnose-01.jpg"

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    ctx = browser.new_context(viewport={"width": 1280, "height": 720},
                              record_video_dir=str(OUT), record_video_size={"width": 1280, "height": 720},
                              locale="zh-CN")
    page = ctx.new_page()
    page.set_default_timeout(20000)

    # 登录
    page.goto(BASE + "/login", wait_until="networkidle")
    time.sleep(2)
    page.fill('input[placeholder="用户名"]', "user")
    page.fill('input[placeholder="密码"]', "User@123")
    page.click(".login-btn")
    page.wait_for_url("**/dashboard", timeout=15000)
    time.sleep(3)

    # 诊断上传页：空态 → 上传 → 扫描 → 结果
    page.goto(BASE + "/diagnosis/upload", wait_until="networkidle")
    time.sleep(2)
    page.set_input_files('input[type="file"]', str(IMG))
    time.sleep(1.2)
    page.locator(".symptom-chip").first.click()
    time.sleep(0.5)
    page.click('button:has-text("开始诊断")')
    time.sleep(3)  # 扫描动画展示
    page.locator(".candidate").first.wait_for(timeout=150000)
    time.sleep(3)
    n = page.locator(".candidate").count()
    print(f"候选数: {n}", flush=True)
    if n > 1:
        page.locator(".candidate").nth(1).click()
        time.sleep(1.5)
        page.locator(".candidate").first.click()
    for label in ("诊断说明", "下一步建议", "图文依据"):
        page.click(f'.el-tabs__item:has-text("{label}")')
        time.sleep(1.5)

    # 来源弹窗（点第一个 KB 编号 chip）
    try:
        page.locator('text=/^KB-[A-Z]+-\\d+$/').first.click()
        time.sleep(2.5)
        page.keyboard.press("Escape")
        time.sleep(0.8)
    except Exception as e:
        print("来源弹窗跳过:", str(e)[:50], flush=True)

    # 知识库页
    page.goto(BASE + "/knowledge", wait_until="networkidle")
    time.sleep(2.5)

    # 智能体对话（真实 LLM）
    page.goto(BASE + "/agent/chat", wait_until="networkidle")
    time.sleep(1.5)
    page.locator("textarea").fill("霜霉病怎么治？")
    page.click('button:has-text("发送")')
    # 等发送按钮进入 loading（确认请求发出），再等它退出 loading（回复完成）
    for _ in range(10):
        if page.locator('button.is-loading:has-text("发送")').count() > 0:
            break
        time.sleep(0.5)
    for _ in range(150):
        if page.locator('button.is-loading:has-text("发送")').count() == 0:
            break
        time.sleep(1)
    time.sleep(4)

    # 诊断记录收尾
    page.goto(BASE + "/diagnosis/records", wait_until="networkidle")
    time.sleep(2.5)

    ctx.close()
    browser.close()

vids = sorted(OUT.glob("*.webm"), key=lambda p: p.stat().st_mtime)
print("视频:", vids[-1] if vids else "未生成", flush=True)
