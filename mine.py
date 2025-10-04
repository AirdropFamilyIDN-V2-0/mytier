
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mine.py  —  Mytier auto by ADFMIDN TEAM
"""
import asyncio, json, time, random, base64, urllib.parse
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple

import aiohttp
from aiohttp import ClientSession, ClientTimeout
from fake_useragent import FakeUserAgent
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, BarColumn, TextColumn, TimeRemainingColumn

# ====== Konfigurasi default ======
BASE = "https://mytier.io"
ACCEPT = "application/json, text/plain, */*"
UA = FakeUserAgent()

AKUN_FILE = Path("akun.txt")
SESS_FILE = Path("sessions.json")

BUFFER_SAFETY = 45            # detik tambahan di atas end_time
MIN_SLACK = 120               # refresh login jika sisa exp JWT <= detik ini
DELAY_MIN = 5                 # jeda antar akun min (detik)
DELAY_MAX = 10                # jeda antar akun max (detik)

console = Console()

@dataclass
class Account:
    nickname: str
    password: str
    cookie_override: Optional[str] = None  # "uid_tt=..."
    uid_cookie: Optional[str] = None       # cached "uid_tt=..."
    checkin: str = "…"
    mining: str = "…"
    next_try: str = "…"

def now_utc() -> datetime:
    return datetime.now(timezone.utc)

def parse_end_time(s: Optional[str]) -> Optional[datetime]:
    if not s: return None
    t = s.strip()
    if not t: return None
    if t.endswith("Z"): t = t[:-1] + "+00:00"
    try:
        if "." in t:
            left, right = t.split(".", 1)
            frac, tz = right.split("+", 1)
            frac = (frac[:6]).ljust(6, "0")
            t = f"{left}.{frac}+{tz}"
        return datetime.fromisoformat(t).astimezone(timezone.utc)
    except Exception:
        return None

def jwt_seconds_left(jwt_token: str) -> Optional[int]:
    try:
        p = jwt_token.split(".")[1]
        p += "=" * (-len(p) % 4)
        payload = json.loads(base64.urlsafe_b64decode(p).decode("utf-8"))
        return int(payload.get("exp", 0)) - int(time.time())
    except Exception:
        return None

def load_accounts() -> List[Account]:
    if not AKUN_FILE.exists():
        AKUN_FILE.write_text("nickname1|password1\nnickname2|password2|uid_tt=PASTE_OPTIONAL\n", encoding="utf-8")
        console.print(Panel("[yellow]Template akun.txt dibuat. Edit dulu lalu jalankan ulang.[/yellow]"))
        raise SystemExit(0)
    accs: List[Account] = []
    for line in AKUN_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"): continue
        parts = line.split("|")
        if len(parts) < 2: continue
        cookie = parts[2].strip() if len(parts) > 2 and parts[2].strip() else None
        accs.append(Account(parts[0].strip(), parts[1].strip(), cookie_override=cookie))
    return accs

def load_sessions() -> Dict[str, str]:
    if SESS_FILE.exists():
        try:
            return json.loads(SESS_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}

def save_sessions(d: Dict[str, str]):
    SESS_FILE.write_text(json.dumps(d, indent=2), encoding="utf-8")

def render_table(accs: List[Account]) -> Table:
    tbl = Table(title="Mytier Auto — By ADFMIDN", show_lines=True)
    tbl.add_column("Nickname", style="cyan", no_wrap=True)
    tbl.add_column("Check-in", style="green")
    tbl.add_column("Mining", style="yellow")
    tbl.add_column("Next Try (UTC)", style="magenta")
    for a in accs:
        tbl.add_row(a.nickname, a.checkin, a.mining, a.next_try)
    return tbl

async def api_login(session: ClientSession, nickname: str, password: str) -> Optional[str]:
    url = f"{BASE}/api/login"
    data = aiohttp.FormData()
    data.add_field("nickname", nickname)
    data.add_field("password", password)
    data.add_field("os", "web")
    headers = {"Accept": ACCEPT, "Origin": BASE, "Referer": f"{BASE}/service/dashboard", "User-Agent": UA.random}
    async with session.post(url, headers=headers, data=data, timeout=60) as r:
        txt = await r.text()
        if r.status != 200:
            console.log(f"[red]{nickname} login failed {r.status}[/red] {txt[:140]}")
            return None
        return txt.strip()

async def get_xsrf(session: ClientSession) -> Tuple[Optional[str], Optional[str]]:
    for path in ("/service/myinfo", "/service/dashboard", "/"):
        try:
            async with session.get(f"{BASE}{path}", headers={"Accept": ACCEPT, "User-Agent": UA.random}, timeout=60) as _:
                for c in session.cookie_jar:
                    if c.key.upper() == "XSRF-TOKEN":
                        raw = c.value
                        try: dec = urllib.parse.unquote(raw)
                        except Exception: dec = raw
                        return raw, dec
        except Exception:
            continue
    return None, None

async def ensure_uid_cookie(session: ClientSession, acc: Account, min_slack: int, cache: Dict[str, str]) -> Optional[str]:
    if acc.cookie_override:
        acc.uid_cookie = acc.cookie_override.strip()
        return acc.uid_cookie
    if not acc.uid_cookie and acc.nickname in cache:
        acc.uid_cookie = cache[acc.nickname]
    if acc.uid_cookie and "uid_tt=" in acc.uid_cookie:
        left = jwt_seconds_left(acc.uid_cookie.split("uid_tt=",1)[1])
        if left is None or left > min_slack:
            return acc.uid_cookie
    token = await api_login(session, acc.nickname, acc.password)
    if not token:
        return None
    acc.uid_cookie = f"uid_tt={token}"
    cache[acc.nickname] = acc.uid_cookie
    save_sessions(cache)
    return acc.uid_cookie

async def attendance_chain(session: ClientSession, acc: Account) -> Tuple[str, str]:
    xsrf_raw, xsrf_hdr = await get_xsrf(session)
    cookie = acc.uid_cookie or ""
    if xsrf_raw:
        cookie = f"{cookie}; XSRF-TOKEN={xsrf_raw}"
    headers = {
        "Accept": ACCEPT,
        "Accept-Language": "en-US,en;q=0.5",
        "Origin": BASE,
        "Referer": f"{BASE}/service/dashboard",
        "User-Agent": UA.random,
        "Content-Type": "application/x-www-form-urlencoded",
        "Content-Length": "0",
        "Cookie": cookie,
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
        "Sec-GPC": "1",
    }
    if xsrf_hdr:
        headers["X-XSRF-TOKEN"] = xsrf_hdr

    async def post(url):
        async with session.post(url, headers=headers, data=b"", timeout=60) as r:
            t = await r.text()
            j = None
            if r.status == 200:
                try: j = await r.json()
                except Exception: pass
            return r.status, t, j

    st1, raw1, j1 = await post(f"{BASE}/api/event_attendance")
    st2, raw2, j2 = await post(f"{BASE}/api/event_attendance_check")

    if st2 == 200 and j2:
        return ("CLAIMED", f"{j2.get('attendance_time')}")
    elif st2 in (403, 405):
        return ("ALREADY TODAY", "—")
    else:
        return (f"ERR {st2}", raw2[:80])

async def mining(session: ClientSession, acc: Account) -> Tuple[str, Optional[datetime]]:
    headers = {
        "Accept": ACCEPT,
        "Origin": BASE,
        "Referer": f"{BASE}/service/dashboard",
        "User-Agent": UA.random,
        "Content-Type": "application/x-www-form-urlencoded",
        "Content-Length": "0",
        "Cookie": acc.uid_cookie or "",
    }
    async with session.post(f"{BASE}/api/mining", headers=headers, data=b"", timeout=60) as r:
        t = await r.text()
        if r.status == 200:
            try: j = await r.json()
            except Exception: j = None
            amt = j.get("amount_mined")
            tot = j.get("total_mining_amount")
            end_dt = parse_end_time(j.get("end_time"))
            return (f"OK mined={amt} total={tot}", end_dt)
        if r.status == 405 and "already" in t.lower():
            return ("ALREADY MINING", now_utc() + timedelta(hours=12))
        return (f"ERR {r.status}", None)

async def countdown(seconds: int, title: str = "Sleeping"):
    if seconds <= 0:
        return
    cap = min(seconds, 24 * 3600)
    with Progress(
        TextColumn(f"[bold]{title}[/bold]"),
        BarColumn(),
        TextColumn("[magenta]{task.completed}/{task.total}s"),
        TextColumn(" • "),
        TimeRemainingColumn(),
        transient=True,
        console=console
    ) as progress:
        task = progress.add_task("", total=cap)
        start = time.time()
        while True:
            elapsed = int(time.time() - start)
            if elapsed >= cap:
                progress.update(task, completed=cap)
                break
            progress.update(task, completed=elapsed)
            await asyncio.sleep(1)

async def process_account(acc: Account, cache: Dict[str, str]):
    timeout = ClientTimeout(total=90)
    async with ClientSession(timeout=timeout) as session:
        # login/refresh
        acc.checkin = "login…"
        console.clear(); console.print(render_table(accounts))
        ck = await ensure_uid_cookie(session, acc, MIN_SLACK, cache)
        if not ck:
            acc.checkin = "[red]LOGIN FAIL[/red]"
            acc.mining = "—"
            acc.next_try = (now_utc() + timedelta(minutes=15)).isoformat()
            console.clear(); console.print(render_table(accounts))
            return

        # attendance chain
        acc.checkin = "attend…"
        console.clear(); console.print(render_table(accounts))
        res, ts = await attendance_chain(session, acc)
        if res == "CLAIMED":
            acc.checkin = f"[green]{res}[/green]"
        elif res == "ALREADY TODAY":
            acc.checkin = f"[green]{res}[/green]"
        else:
            acc.checkin = f"[red]{res}[/red]"
        console.clear(); console.print(render_table(accounts))

        # mining
        acc.mining = "mining…"
        console.clear(); console.print(render_table(accounts))
        mres, end_dt = await mining(session, acc)
        if mres.startswith("OK"):
            acc.mining = f"[yellow]{mres}[/yellow]"
        elif mres == "ALREADY MINING":
            acc.mining = f"[yellow]{mres}[/yellow]"
        else:
            acc.mining = f"[red]{mres}[/red]"

        # next try
        wait_seconds = 12 * 3600 + BUFFER_SAFETY
        if end_dt:
            wait_seconds = max(0, int((end_dt - now_utc()).total_seconds())) + BUFFER_SAFETY
        acc.next_try = (now_utc() + timedelta(seconds=wait_seconds)).isoformat()
        console.clear(); console.print(render_table(accounts))

async def main():
    global accounts
    accounts = load_accounts()
    cache = load_sessions()

    while True:
        for acc in accounts:
            await process_account(acc, cache)
            d = random.uniform(DELAY_MIN, DELAY_MAX)
            await countdown(int(d), title=f"Waiting before next account ({acc.nickname} done)")

        def parse_iso(s):
            try: return datetime.fromisoformat(s)
            except Exception: return now_utc() + timedelta(minutes=30)
        next_times = [parse_iso(a.next_try) for a in accounts if a.next_try != "…"]
        if not next_times:
            sleep_sec = 1800
        else:
            sleep_sec = max(10, int((min(next_times) - now_utc()).total_seconds()))
        await countdown(sleep_sec, title="Round done. Sleeping until next round")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n[bold]Bye[/bold]")
