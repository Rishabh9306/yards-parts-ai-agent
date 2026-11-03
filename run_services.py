import subprocess
import time
import re
import os
import sys

base_dir = os.path.dirname(os.path.abspath(__file__))
if not base_dir:
    base_dir = os.getcwd()
os.chdir(base_dir)

# Clean up any lingering python uvicorn on port 8000 or cloudflared
def cleanup_old_processes():
    try:
        out = subprocess.check_output('netstat -ano | findstr :8000', shell=True).decode()
        for line in out.splitlines():
            parts = line.strip().split()
            if len(parts) >= 5 and "LISTENING" in line:
                pid = parts[-1]
                print(f"[Supervisor Cleanup] Terminating old process on port 8000 (PID {pid})...")
                subprocess.run(f"taskkill /F /PID {pid}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass
    try:
        subprocess.run("taskkill /F /IM cloudflared.exe", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass

cleanup_old_processes()
time.sleep(1)

print("[Supervisor] Starting Cloudflare Tunnel...")
_local_cf = os.path.join(base_dir, "cloudflared.exe")
if os.path.exists(r"C:\Program Files (x86)\cloudflared\cloudflared.exe"):
    cloudflared_bin = r"C:\Program Files (x86)\cloudflared\cloudflared.exe"
elif os.path.exists(_local_cf):
    cloudflared_bin = _local_cf
else:
    cloudflared_bin = "cloudflared"
cf_proc = subprocess.Popen(
    [cloudflared_bin, "tunnel", "--no-autoupdate", "--edge-ip-version", "4", "--protocol", "http2", "--url", "http://127.0.0.1:8000"],
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
    encoding="utf-8",
    errors="replace",
    bufsize=1
)

tunnel_url = None
start_time = time.time()
while time.time() - start_time < 30:
    line = cf_proc.stdout.readline()
    if not line:
        break
    print(f"[cloudflared] {line.strip()}")
    m = re.search(r'https://[a-zA-Z0-9-]+\.trycloudflare\.com', line)
    if m:
        tunnel_url = m.group(0)
        break

if not tunnel_url:
    print("[Supervisor ERROR] Failed to obtain tunnel URL!")
    sys.exit(1)

print(f"\n[Supervisor SUCCESS] Live Webhook Public URL: {tunnel_url}\n")
os.environ["TWIML_BASE_URL"] = tunnel_url

# Update .env
env_path = os.path.join(base_dir, ".env")
with open(env_path, "r", encoding="utf-8") as f:
    text = f.read()

text = re.sub(r"TWIML_BASE_URL=.*", f"TWIML_BASE_URL={tunnel_url}", text)
with open(env_path, "w", encoding="utf-8", newline="\n") as f:
    f.write(text)

# Also update twilio_voice.py fallback
tv_path = os.path.join(base_dir, "app", "comms", "twilio_voice.py")
with open(tv_path, "r", encoding="utf-8") as f:
    tv_text = f.read()

tv_text = re.sub(
    r'TWIML_BASE_URL = os\.getenv\("TWIML_BASE_URL",\s*"[^"]*"\)',
    f'TWIML_BASE_URL = os.getenv("TWIML_BASE_URL", "{tunnel_url}")',
    tv_text
)
with open(tv_path, "w", encoding="utf-8", newline="\n") as f:
    f.write(tv_text)

# Also update main.py fallback
m_path = os.path.join(base_dir, "app", "main.py")
with open(m_path, "r", encoding="utf-8") as f:
    m_text = f.read()

m_text = re.sub(
    r'TWIML_BASE_URL = os\.getenv\("TWIML_BASE_URL",\s*"[^"]*"\)',
    f'TWIML_BASE_URL = os.getenv("TWIML_BASE_URL", "{tunnel_url}")',
    m_text
)
with open(m_path, "w", encoding="utf-8", newline="\n") as f:
    f.write(m_text)

print("[Supervisor] .env, twilio_voice.py, and main.py updated with active tunnel!")

# Now start Uvicorn with the live TWIML_BASE_URL in its environment!
app_env = os.environ.copy()
app_env["TWIML_BASE_URL"] = tunnel_url

print("[Supervisor] Starting Uvicorn server on 127.0.0.1:8000 (with --reload)...")
uvicorn_proc = subprocess.Popen(
    [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000", "--reload"],
    cwd=base_dir,
    env=app_env,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL
)

time.sleep(2)
print("[Supervisor] Unified services running smoothly.")

# Drain output and stay alive
try:
    while True:
        try:
            line = cf_proc.stdout.readline()
            if line:
                if "GET " in line or "POST " in line or "ERR" in line:
                    print(f"[Tunnel Request] {line.strip()}")
        except Exception:
            pass
        time.sleep(1)
except (KeyboardInterrupt, SystemExit):
    print("[Supervisor] Received termination signal.")
except Exception as e:
    print(f"[Supervisor Exiting]: {e}")
finally:
    try: uvicorn_proc.terminate()
    except Exception: pass
    try: cf_proc.terminate()
    except Exception: pass
