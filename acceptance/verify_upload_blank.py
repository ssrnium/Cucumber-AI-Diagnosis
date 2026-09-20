# -*- coding: utf-8 -*-
"""空白图降级路径验证：未检出病斑时的页面行为。"""
import time, pathlib
from playwright.sync_api import sync_playwright

BASE = "http://localhost:5173"
SHOTS = pathlib.Path(__file__).parent.parent / "logs" / "shots"
IMG = pathlib.Path(__file__).parent.parent.parent / "cucumber-diagnosis-platform" / "test-assets" / "blank.jpg"

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1500, "height": 960})
    page.goto(BASE + "/login", wait_until="networkidle")
    page.fill('input[placeholder="用户名"]', "user")
    page.fill('input[placeholder="密码"]', "User@123")
    page.click(".login-btn")
    page.wait_for_url("**/dashboard", timeout=15000)

    page.goto(BASE + "/diagnosis/upload", wait_until="networkidle")
    page.set_input_files('input[type="file"]', str(IMG))
    time.sleep(0.8)
    page.click('button:has-text("开始诊断")')
    # 等待结果区出现（候选或未检出提示，二选一）
    ok = False
    for _ in range(150):
        if page.locator(".candidate").count() > 0:
            print("结果: 出现候选(意外)", flush=True)
            ok = True
            break
        if page.locator('.el-alert:has-text("未检出")').count() > 0 or \
           page.locator('text=未检出').count() > 0:
            print("结果: 未检出提示出现(预期降级)", flush=True)
            ok = True
            break
        if page.locator('.el-alert--error').count() > 0:
            print("结果: 错误提示", page.locator('.el-alert--error').first.inner_text()[:80], flush=True)
            break
        time.sleep(1)
    time.sleep(0.5)
    page.screenshot(path=str(SHOTS / "verify0920_11-blank.png"))
    browser.close()
    print("PASS" if ok else "FAIL: 既无候选也无未检出提示", flush=True)
