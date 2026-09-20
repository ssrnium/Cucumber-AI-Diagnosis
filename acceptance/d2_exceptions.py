# -*- coding: utf-8 -*-
"""D2 异常场景验收：未登录/错误文件/AI 不可用/LLM 降级/重复提交/DB 故障/Redis 降级/空数据态。
运行：tools/pw-venv/Scripts/python.exe tools/acceptance/d2_exceptions.py
注意：会真实停启 ai(8000)/agent(8002)/PG/Redis，结束后全部恢复。
"""
import os, subprocess, sys, time, pathlib
import httpx
from playwright.sync_api import sync_playwright

BASE = "http://localhost:5173"
ADMIN = "http://127.0.0.1:8080"
AI = "http://127.0.0.1:8000"
AGENT = "http://127.0.0.1:8002"
PROJ = pathlib.Path(__file__).parent.parent.parent / "cucumber-diagnosis-platform"
LOGS = pathlib.Path(__file__).parent.parent / "logs"
SHOTS = LOGS / "shots"
SHOTS.mkdir(parents=True, exist_ok=True)
IMG = PROJ / "test-assets" / "leaf-anthracnose-01.jpg"
PSQL = r"<user-home>\pgsql16\bin\psql.exe"
PG_ISREADY = r"<user-home>\pgsql16\bin\pg_isready.exe"
PGCTL = r"<user-home>\pgsql16\bin\pg_ctl.exe"
PGDATA = r"<user-home>\pgdata"
PG_EXE = r"<user-home>\pgsql16\bin\postgres.exe"
IMG_BYTES = open(IMG, "rb").read()

# 直连本地，不信任系统代理环境变量
HTTP = httpx.Client(trust_env=False, timeout=30)
HTTP_LONG = httpx.Client(trust_env=False, timeout=180)

RESULTS = []
def check(name, cond, extra=""):
    RESULTS.append((name, bool(cond), extra))
    print(f'{"✓" if cond else "✗"} {name} {extra}', flush=True)

def login_token(u, p):
    r = HTTP.post(f"{ADMIN}/api/v1/auth/login", json={"username": u, "password": p})
    return r.json()["data"]["token"]

def kill_pid_on_port(port):
    r = subprocess.run(["netstat", "-ano"], capture_output=True)
    out = (r.stdout or b"").decode("utf-8", errors="ignore")
    pids = set()
    for line in out.splitlines():
        if f":{port}" in line and "LISTENING" in line:
            pids.add(line.split()[-1])
    for pid in pids:
        subprocess.run(["taskkill", "/PID", pid, "/F"], capture_output=True)
    return len(pids)

def wait_up(url, timeout=90):
    for _ in range(timeout):
        try:
            if HTTP.get(url, timeout=2).status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(1)
    return False

def wait_down(url, timeout=20):
    for _ in range(timeout):
        try:
            HTTP.get(url, timeout=2)
        except Exception:
            return True
        time.sleep(1)
    return False

def start_ai(env_extra=None):
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    if env_extra:
        env.update(env_extra)
    log = open(LOGS / "ai.log", "ab")
    subprocess.Popen([str(PROJ / "cucumber-ai/.venv/Scripts/python.exe"), "-m", "uvicorn",
                      "app.main:app", "--host", "127.0.0.1", "--port", "8000"],
                     cwd=str(PROJ / "cucumber-ai"), env=env, stdout=log, stderr=log,
                     creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)

def start_agent():
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    for line in (PROJ / "cucumber-agent/.env").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    log = open(LOGS / "agent.log", "ab")
    subprocess.Popen([str(PROJ / "cucumber-agent/.venv/Scripts/python.exe"), "api/main.py"],
                     cwd=str(PROJ / "cucumber-agent/echomind"), env=env, stdout=log, stderr=log,
                     creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)

user_t = login_token("user", "User@123")
admin_t = login_token("admin", "Admin@123")
HU, HA = {"Authorization": f"Bearer {user_t}"}, {"Authorization": f"Bearer {admin_t}"}

# ── A. 基础异常 ─────────────────────────────────────
r = HTTP.get(f"{ADMIN}/api/v1/diagnosis")
check("A1 未登录访问受保护接口 → 401", r.json().get("code") == 401, f"code={r.json().get('code')}")

r = HTTP.post(f"{ADMIN}/api/v1/diagnosis", files={"file": ("x.txt", b"hello", "text/plain")}, headers=HU)
check("A2 错误文件类型被拒", r.json().get("code") != 200 and "图片" in r.json().get("message", ""),
      f"code={r.json().get('code')} msg={r.json().get('message')}")

# ── B. AI 服务不可用 ────────────────────────────────
kill_pid_on_port(8000)
check("B0 AI 进程已停止", wait_down(f"{AI}/health", 20), "")
r = HTTP.post(f"{ADMIN}/api/v1/diagnosis", files={"file": ("leaf.jpg", IMG_BYTES, "image/jpeg")}, headers=HU, timeout=90)
d = r.json()
db_status = subprocess.run([PSQL, "-U", "postgres", "-h", "127.0.0.1", "-d", "cucumber_db", "-tAc",
                            "SELECT status FROM diagnosis_record ORDER BY id DESC LIMIT 1"],
                           capture_output=True, text=True).stdout.strip()
check("B1 AI 宕机→友好错误+记录 FAILED 落库",
      d.get("code") != 200 and "暂不可用" in d.get("message", "") and db_status == "FAILED",
      f"msg={d.get('message')} db={db_status}")

# ── C. LLM 不可用 → 骨架降级报告 ───────────────────────
start_ai({"LLM_PROVIDER": "kimi", "KIMI_API_KEY": "invalid-key-for-degradation-test"})
if wait_up(f"{AI}/health", 60):
    det = HTTP.post(f"{AI}/api/v1/detect", files={"file": ("leaf.jpg", IMG_BYTES, "image/jpeg")}).json()
    rr = HTTP_LONG.post(f"{AI}/api/v1/diagnose", json={"detections": det.get("detections")})
    rep = rr.json()
    keys = list(rep.keys()) if isinstance(rep, dict) else []
    check("C1 LLM 宕机→骨架降级报告仍产出",
          rr.status_code == 200 and "disease_type" in keys and len(rep.get("basis") or []) > 0,
          f"keys={keys[:6]} basis_len={len(rep.get('basis') or []) if isinstance(rep, dict) else 0}")
else:
    check("C1 LLM 宕机→骨架降级报告仍产出", False, "ai 带错误 key 启动失败")
kill_pid_on_port(8000)
wait_down(f"{AI}/health", 20)
start_ai()
check("C2 AI 服务恢复(mock)", wait_up(f"{AI}/health", 60), "")

# ── D. 智能体服务不可用 → admin 代理友好错误 ─────────────
kill_pid_on_port(8002)
check("D0 agent 进程已停止", wait_down(f"{AGENT}/health", 20), "")
r = HTTP.post(f"{ADMIN}/api/v1/agent/chat", json={"message": "霜霉病怎么治", "session_id": "d2-exc"}, headers=HU, timeout=30)
check("D1 agent 宕机→友好错误", r.json().get("code") != 200 and bool(r.json().get("message")),
      f"code={r.json().get('code')} msg={r.json().get('message')}")
start_agent()
check("D2 agent 服务恢复", wait_up(f"{AGENT}/health", 90), "")

# ── E. 数据库故障与恢复 ───────────────────────────────
kill_pid_on_port(5432)
time.sleep(3)
pg_down = subprocess.run([PG_ISREADY, "-U", "postgres", "-h", "127.0.0.1"],
                         capture_output=True).returncode != 0
check("E0 PG 已停止", pg_down, "")
try:
    # HikariCP 默认连接超时 30s：DB 宕机时请求会先阻塞再返回 500，客户端要给足等待
    r = HTTP.get(f"{ADMIN}/api/v1/diagnosis?page=1&size=3", headers=HU, timeout=50)
    check("E1 DB 宕机→友好错误格式（非堆栈）", r.json().get("code") == 500 and "系统繁忙" in r.json().get("message", ""),
          f"msg={r.json().get('message')}")
except Exception as e:
    check("E1 DB 宕机→友好错误格式（非堆栈）", False, f"请求异常 {str(e)[:60]}")
# pg_ctl 会降权启动 postmaster（postgres.exe 直接跑会拒绝管理员权限）；
# 用 cmd start /b 让 pg_ctl 脱离本进程树，避免脚本退出时 PG 被回收
os.system(f'cmd /c start /b "" "{PGCTL}" -D "{PGDATA}" -l "<user-home>\\pgdata\\server.log" -W start')
time.sleep(2)
pg_ok = False
for _ in range(40):
    rr = subprocess.run([PG_ISREADY, "-U", "postgres", "-h", "127.0.0.1"], capture_output=True)
    if rr.returncode == 0:
        pg_ok = True
        break
    time.sleep(1)
time.sleep(5)  # 等连接池重建
try:
    r = HTTP.get(f"{ADMIN}/api/v1/diagnosis?page=1&size=3", headers=HU, timeout=15)
    check("E2 DB 恢复→接口恢复", pg_ok and r.json().get("code") == 200, f"pg_up={pg_ok} code={r.json().get('code')}")
except Exception as e:
    check("E2 DB 恢复→接口恢复", False, f"{str(e)[:60]} pg_up={pg_ok}")

# ── F. Redis 宕机 → 降级 ───────────────────────────────
kill_pid_on_port(6379)
time.sleep(2)
try:
    r = HTTP.post(f"{ADMIN}/api/v1/auth/login", json={"username": "user", "password": "User@123"}, timeout=15)
    check("F1 Redis 宕机→admin 登录不受影响（JWT 无状态）", r.json().get("code") == 200, "")
except Exception as e:
    check("F1 Redis 宕机→admin 登录不受影响（JWT 无状态）", False, str(e)[:60])
try:
    r = HTTP_LONG.post(f"{AGENT}/chat", json={"message": "你好", "user_id": "d2-redis", "conv_id": "d2-redis"})
    check("F2 Redis 宕机→agent 降级仍可应答", r.status_code == 200 and len(r.text) > 20, f"HTTP {r.status_code}")
except Exception as e:
    check("F2 Redis 宕机→agent 降级仍可应答", False, str(e)[:60])
subprocess.Popen([str(pathlib.Path(__file__).parent.parent / "redis" / "redis-server.exe"), "--port", "6379", "--bind", "127.0.0.1"],
                 cwd=str(pathlib.Path(__file__).parent.parent / "redis"),
                 stdout=open(LOGS / "redis.log", "ab"), stderr=subprocess.STDOUT,
                 creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
time.sleep(3)

# ── G. 浏览器：空数据态 + 重复提交提示 ───────────────────
with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    page = browser.new_context(viewport={"width": 1500, "height": 900}, locale="zh-CN").new_page()

    r = HTTP.post(f"{ADMIN}/api/v1/system/user", json={"username": "empty_user", "password": "Empty@123", "nickname": "空数据验收"}, headers=HA, timeout=15)
    check("G0 准备空用户", r.json().get("code") == 200 or "已存在" in r.json().get("message", ""), "")

    page.goto(BASE + "/login", wait_until="networkidle")
    page.fill('input[placeholder="用户名"]', "empty_user")
    page.fill('input[placeholder="密码"]', "Empty@123")
    page.click(".login-btn")
    page.wait_for_url("**/dashboard", timeout=15000)
    page.goto(BASE + "/diagnosis/records", wait_until="networkidle")
    time.sleep(2)
    body = page.locator("body").inner_text()
    check("G1 空数据态（无记录提示）", "暂无数据" in body or "暂无" in body, "")
    page.screenshot(path=str(SHOTS / "g1-empty-records.png"))

    page.evaluate("localStorage.clear()")
    page.goto(BASE + "/login", wait_until="networkidle")
    page.fill('input[placeholder="用户名"]', "user")
    page.fill('input[placeholder="密码"]', "User@123")
    page.click(".login-btn")
    page.wait_for_url("**/dashboard", timeout=15000)
    page.goto(BASE + "/diagnosis/upload", wait_until="networkidle")
    page.set_input_files('input[type="file"]', str(IMG))
    time.sleep(0.5)
    with page.expect_response(lambda r: "/api/v1/diagnosis" in r.url and r.request.method == "POST", timeout=90000) as r1i:
        page.click('.action-bar button:has-text("开始诊断")')
    first = r1i.value.json().get("data") or {}
    page.wait_for_selector(".detect-box, .el-alert", timeout=30000)
    page.set_input_files('input[type="file"]', str(IMG))
    time.sleep(0.5)
    with page.expect_response(lambda r: "/api/v1/diagnosis" in r.url and r.request.method == "POST", timeout=90000) as r2i:
        page.click('.action-bar button:has-text("开始诊断")')
    second = r2i.value.json().get("data") or {}
    check("G2 浏览器重复提交 → duplicated 命中", second.get("duplicated") == True and second.get("record_no") == first.get("record_no"),
          f"dup={second.get('duplicated')}")
    page.screenshot(path=str(SHOTS / "g2-duplicate.png"))
    browser.close()

fails = [r for r in RESULTS if not r[1]]
print(f"\n==== D2 汇总：{len(RESULTS) - len(fails)}/{len(RESULTS)} 通过 ====")
for n, c, e in fails:
    print(f"未过项: {n} {e}")
sys.exit(1 if fails else 0)
