#!/usr/bin/env python3
"""사이드바 부서 카드(조직도) 회귀 게이트 (수동 실행 — CI 미배선).

검증 항목 (2026-09-24 오너 요청 — 한우리 송파 독서논술 교육연구부 = dept-1):
  1. 부서 카드: 부서 표시명 + "정상 n/m" + 역할 노드 4개가 부장→CSO→워커→리뷰어 순서로 직원 목록.
  2. 행마다 한글 직책·내부 역할명·surface id·상태 라벨·5색 dot·작업명/대기·진행률(귀속 TODO)·CTX.
  3. 상태는 org.status 원신호로만 판정(관문 표식·자기보고 부재·종료 → 주황·노랑·회색).
  4. 접기/펼치기: 접혀도 "정상 n/m" 유지 · localStorage(cys-org-collapsed) 영속·리로드 복원.
  5. 행 클릭 = 그 부서 워크스페이스로 전환 + 그 pane 포커스(.pane.focused).
  6. 상태 갱신: 데몬 이벤트 → org_status 재조회 → 색·집계 반영 · 사라진 노드 = 회색 '연결 끊김'(직책 유지).
  7. 부서 데몬 조회 실패 = 직전 신호를 정상으로 칠하지 않는다(전원 회색 · 정상 0/4).
  8. 기존 기능 회귀: 탭 클릭 전환 · 더블클릭 이름 변경 · 승인 배지 · 콘솔 pageerror 0.

사전: sh ui/build.sh · pip install playwright (시스템 Edge 채널 사용 — chromium 다운로드 불필요)
실행: python3 ui/e2e/orgcard_gate.py   # exit 0 = PASS · 스크린샷 ui/e2e/out/orgcard-*.png
"""
import http.server
import json
import socket
import sys
import threading
from pathlib import Path

DIST = Path(__file__).resolve().parent.parent / "dist"
OUT = Path(__file__).resolve().parent / "out"
DEPT = "\\\\.\\pipe\\cys-dept-dept-1"

LAYOUT = {
    "workspaces": [
        {"id": 1, "name": "non title", "tree": {"type": "pane", "sid": 90}},
        {"id": 2, "name": "한우리 송파 독서논술 교육연구부", "socket": DEPT, "tree": {
            "type": "split", "dir": "row", "ratio": 0.45,
            "a": {"type": "split", "dir": "col", "ratio": 0.75,
                  "a": {"type": "pane", "sid": 4}, "b": {"type": "pane", "sid": 5}},
            "b": {"type": "split", "dir": "row", "ratio": 0.5,
                  "a": {"type": "pane", "sid": 6}, "b": {"type": "pane", "sid": 7}}}},
    ],
    "groups": [], "active": 1, "counter": 3, "groupCounter": 1,
}

# 2026-09-24 dept-1 org.status 실측 형상(필드 동일 · 값 발췌).
def node(sid, role, **kw):
    n = {"surface_id": sid, "surface_ref": f"surface:{sid}", "role": role, "agent": "claude",
         "agent_alive": True, "exited": False, "gate_pending": None, "idle_secs": 30,
         "awakened_at": 1790150967.1, "status": None, "usage": None, "title": f"{role}"}
    n.update(kw)
    return n

DEPT_ORG = {
    "surfaces": [
        node(4, "master", status={"age_secs": 90, "context_pct": None, "state": "waiting",
             "task": "한우리 교육연구부장 · 한우리 송파 독서논술 교육연구부 · 임무 대기"},
             usage={"ctx_pct": 19}),
        node(5, "cso", status={"age_secs": 1878, "context_pct": 17, "state": "waiting", "task": None}),
        node(6, "worker", status={"age_secs": 27758, "context_pct": 5, "state": "waiting",
             "task": "각성 완료 · 임무 대기"},
             gate_pending={"gate": "gate_pending_stale", "since": 1790055804.4, "evidence": "…"}),
        node(7, "reviewer-codex", agent="codex", awakened_at=None),
    ],
    "feed": {"pending": 0},
    "todo": {
        "C:\\p\\CSO_TODO.md": {"owner": "cso", "done": 20, "total": 32, "verdict": "counted"},
        "C:\\p\\MASTER_TODO.md": {"done": 0, "total": 1, "verdict": "unclaimed"},
    },
}
BASE_ORG = {
    "surfaces": [node(90, "master", status={"age_secs": 5, "context_pct": 40, "state": "working",
                                            "task": "본부 운영"})],
    "feed": {"pending": 2}, "todo": {},
}

SHIM = """
(() => {
  const DEPT = %(dept)s;
  window.__ORG = { dept: %(dept_org)s, base: %(base_org)s, deptFail: false };
  const L = {};
  window.__emit = (name, payload) => (L[name] || []).forEach((h) => h({ payload }));
  const surf = (o) => ({ surfaces: o.surfaces.map((s) => ({ surface_id: s.surface_id, title: s.title, exited: !!s.exited, role: s.role })) });
  const isDept = (a) => a && a.socket === DEPT;
  window.__TAURI__ = {
    core: { invoke: (c, a) => {
      switch (c) {
        case "daemon_status": return Promise.resolve({ daemon_pid: 1, socket_path: "mock" });
        case "list_depts": return Promise.resolve({ depts: { "dept-1": { socket: DEPT, display_name: "한우리 송파 독서논술 교육연구부" } } });
        case "dept_tombstones": return Promise.resolve([]);
        case "list_surfaces": return Promise.resolve(surf(isDept(a) ? window.__ORG.dept : window.__ORG.base));
        case "org_status":
          if (isDept(a) && window.__ORG.deptFail) return Promise.reject("mock: dept daemon down");
          return Promise.resolve(JSON.parse(JSON.stringify(isDept(a) ? window.__ORG.dept : window.__ORG.base)));
        case "start_surface_stream": case "resize_surface": case "ceo_pending": return Promise.resolve(null);
        case "feed_list": return Promise.resolve({ items: [] });
        case "attach_surface": return Promise.resolve({ output_event: `out-${a.surfaceId}`, exited_event: `exit-${a.surfaceId}` });
        default: return Promise.resolve(null);
      }
    } },
    event: { listen: (n, h) => { (L[n] = L[n] || []).push(h); return Promise.resolve(() => {}); } },
  };
  if (!localStorage.getItem("cys-layout-v2")) localStorage.setItem("cys-layout-v2", %(layout)s);
})();
""" % {
    "dept": json.dumps(DEPT),
    "dept_org": json.dumps(DEPT_ORG, ensure_ascii=False),
    "base_org": json.dumps(BASE_ORG, ensure_ascii=False),
    "layout": json.dumps(json.dumps(LAYOUT, ensure_ascii=False), ensure_ascii=False),
}

failures: list[str] = []

def check(cond: bool, msg: str) -> None:
    print(f"  [{'PASS' if cond else 'FAIL'}] {msg}")
    if not cond:
        failures.append(msg)

DEPT_TAB = '#ws-tabs .ws-tab[data-ws-id="2"]'
BASE_TAB = '#ws-tabs .ws-tab[data-ws-id="1"]'

ROWS_JS = """(sel) => [...document.querySelectorAll(sel + ' .ws-org-row')].map((r) => ({
  sid: r.dataset.orgSid,
  title: r.querySelector('.ws-org-title').textContent,
  role: r.querySelector('.ws-org-role').textContent,
  sidText: r.querySelector('.ws-org-sid').textContent,
  tone: [...r.querySelector('.ws-org-dot').classList].find((c) => c.startsWith('tone-')),
  dotColor: getComputedStyle(r.querySelector('.ws-org-dot')).backgroundColor,
  line: r.querySelector('.ws-org-text').textContent,
}))"""

def rows(pg, sel=DEPT_TAB):
    return pg.evaluate(ROWS_JS, sel)

def count(pg, sel=DEPT_TAB):
    return pg.evaluate("(s) => document.querySelector(s + ' .ws-org-count')?.textContent ?? null", sel)

def refresh(pg):
    # 데몬 이벤트(pane.idle) → onDaemonEvent → refreshSidebarStatus (10초 폴링을 기다리지 않는다)
    pg.evaluate("window.__emit('daemon-event', { name: 'pane.idle', category: 'info', surface_id: 6, payload: { idle_seconds: 61 } })")
    pg.wait_for_timeout(400)

def main() -> int:
    if not (DIST / "index.html").exists():
        print("FAIL: ui/dist 없음 — 먼저 `sh ui/build.sh`")
        return 2
    from playwright.sync_api import sync_playwright
    OUT.mkdir(exist_ok=True)
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]
    handler = lambda *a, **kw: http.server.SimpleHTTPRequestHandler(*a, directory=str(DIST), **kw)
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        with sync_playwright() as pw:
            b = pw.chromium.launch(channel="msedge")
            pg = b.new_page(viewport={"width": 1400, "height": 900})
            pg.add_init_script(SHIM)
            errs: list[str] = []
            pg.on("pageerror", lambda e: errs.append(str(e)[:200]))
            pg.goto(f"http://127.0.0.1:{port}/index.html")
            pg.wait_for_selector(f"{DEPT_TAB} .ws-org-row", timeout=15000)
            pg.wait_for_timeout(200)
            pg.locator("#wsbar").screenshot(path=str(OUT / "orgcard-1-initial.png"))

            print("1·2·3. 부서 카드 · 행 · 원신호 판정")
            check(pg.inner_text(f"{DEPT_TAB} .ws-name") == "한우리 송파 독서논술 교육연구부", "부서 표시명")
            check(count(pg) == "정상 2/4", f"정상 2/4 (got {count(pg)})")
            check(pg.evaluate(f"document.querySelector('{DEPT_TAB} .ws-org-count').classList.contains('degraded')"),
                  "비정상 노드가 있으면 집계 강조(degraded)")
            r = rows(pg)
            check([x["sid"] for x in r] == ["4", "5", "6", "7"], f"순서 부장→CSO→워커→리뷰어 (got {[x['sid'] for x in r]})")
            check([x["title"] for x in r] == ["한우리 교육연구부장", "교육과정 운영실장", "독서토론논술 수업연구원", "수업·교재 품질검토관"],
                  f"한글 직책 4종 (got {[x['title'] for x in r]})")
            check([x["role"] for x in r] == ["master", "CSO", "worker", "reviewer"], f"내부 역할명 (got {[x['role'] for x in r]})")
            check([x["sidText"] for x in r] == ["#4", "#5", "#6", "#7"], "surface id 표시")
            check([x["tone"] for x in r] == ["tone-waiting", "tone-waiting", "tone-attention", "tone-starting"],
                  f"5색 판정 파랑·파랑·주황(낡은 관문)·노랑(각성 미확인) (got {[x['tone'] for x in r]})")
            check(r[0]["dotColor"] == "rgb(88, 166, 255)", f"대기 = 파란 dot (got {r[0]['dotColor']})")
            check(r[2]["dotColor"] == "rgb(240, 136, 62)", f"확인 필요 = 주황 dot (got {r[2]['dotColor']})")
            check(r[3]["dotColor"] == "rgb(227, 179, 65)", f"시작 = 노란 dot (got {r[3]['dotColor']})")
            check("대기 중" in r[0]["line"] and "임무 대기" in r[0]["line"] and "CTX 19%" in r[0]["line"],
                  f"부장 행: 상태·작업명·CTX (got {r[0]['line']})")
            check(r[1]["line"] == "대기 중 · 진행 63% · CTX 17%",
                  f"CSO 행: 대기·귀속 TODO 진행률 20/32=63%·CTX (got {r[1]['line']})")
            check("진행" not in r[0]["line"], "귀속 안 된(unclaimed) TODO 는 진행률 미표시")
            check(r[2]["line"].startswith("확인 필요(관문 표식)"), f"워커 행 (got {r[2]['line']})")
            check(r[3]["line"] == "각성 미확인", f"리뷰어 행 (got {r[3]['line']})")
            check(count(pg, BASE_TAB) == "정상 1/1" and rows(pg, BASE_TAB)[0]["title"] == "마스터",
                  "본부 카드: 기본 직책(마스터) · 정상 1/1")
            check(rows(pg, BASE_TAB)[0]["tone"] == "tone-working" and
                  rows(pg, BASE_TAB)[0]["dotColor"] == "rgb(63, 185, 80)", "작업 중 = 초록 dot")

            print("4. 접기/펼치기")
            pg.click(f"{DEPT_TAB} .ws-org-chevron"); pg.wait_for_timeout(150)
            check(len(rows(pg)) == 0, "접으면 직원 목록 숨김")
            check(count(pg) == "정상 2/4", "접혀도 정상 2/4 유지")
            check(pg.evaluate("localStorage.getItem('cys-org-collapsed')") == "[2]", "접힘 영속(localStorage)")
            pg.locator("#wsbar").screenshot(path=str(OUT / "orgcard-2-collapsed.png"))
            pg.reload(); pg.wait_for_selector(f"{DEPT_TAB} .ws-org-count", timeout=15000)
            check(len(rows(pg)) == 0 and count(pg) == "정상 2/4", "리로드 후 접힘 복원")
            pg.click(f"{DEPT_TAB} .ws-org-chevron"); pg.wait_for_timeout(150)
            check(len(rows(pg)) == 4, "펼치면 4행 복귀")
            check(pg.evaluate("localStorage.getItem('cys-org-collapsed')") == "[]", "펼침 영속")

            print("5. 행 클릭 = pane 이동 · 기존 탭 전환 회귀")
            pg.click(f"{BASE_TAB} .ws-name"); pg.wait_for_timeout(200)
            check(pg.evaluate(f"document.querySelector('{BASE_TAB}').classList.contains('active')"), "탭 클릭 = 워크스페이스 전환(회귀)")
            pg.click(f'{DEPT_TAB} .ws-org-row[data-org-sid="6"]'); pg.wait_for_timeout(250)
            check(pg.evaluate(f"document.querySelector('{DEPT_TAB}').classList.contains('active')"), "행 클릭 = 부서 워크스페이스로 전환")
            check(pg.evaluate("!!document.querySelector('.pane[data-sid=\"6\"].focused')"), "행 클릭 = 그 pane(#6) 포커스")
            pg.click(f'{DEPT_TAB} .ws-org-row[data-org-sid="4"]'); pg.wait_for_timeout(200)
            check(pg.evaluate("!!document.querySelector('.pane[data-sid=\"4\"].focused')"), "같은 부서 안 다른 행(#4)으로 포커스 이동")

            print("6. 상태 갱신 · 사라진 노드")
            pg.evaluate("""(() => { const d = window.__ORG.dept;
              const w = d.surfaces.find((s) => s.surface_id === 6); w.gate_pending = null; w.status.state = 'working'; w.status.task = '3학년 독서토론 수업안 작성';
              const rv = d.surfaces.find((s) => s.surface_id === 7); rv.exited = true; })()""")
            refresh(pg)
            r = rows(pg)
            check(r[2]["tone"] == "tone-working" and "3학년 독서토론 수업안 작성" in r[2]["line"], f"워커 → 작업 중·작업명 (got {r[2]['line']})")
            check(r[3]["tone"] == "tone-down" and r[3]["line"].startswith("종료"), f"리뷰어 exited → 회색 종료 (got {r[3]['line']})")
            check(count(pg) == "정상 3/4", f"정상 3/4 (got {count(pg)})")
            pg.locator("#wsbar").screenshot(path=str(OUT / "orgcard-3-updated.png"))
            pg.evaluate("window.__ORG.dept.surfaces = window.__ORG.dept.surfaces.filter((s) => s.surface_id !== 5)")
            refresh(pg)
            r = rows(pg)
            cso = next((x for x in r if x["sid"] == "5"), None)
            check(cso is not None and cso["tone"] == "tone-down" and cso["title"] == "교육과정 운영실장",
                  f"사라진 노드 = 회색 연결 끊김 · 직책 유지 (got {cso})")
            check(count(pg) == "정상 2/4", f"정상 2/4 (got {count(pg)})")

            print("7. 부서 데몬 조회 실패")
            pg.evaluate("window.__ORG.deptFail = true"); refresh(pg)
            r = rows(pg)
            check(len(r) == 4 and all(x["tone"] == "tone-down" for x in r), f"조회 실패 = 전원 회색 (got {[x['tone'] for x in r]})")
            check(count(pg) == "정상 0/4", f"정상 0/4 (got {count(pg)})")
            pg.evaluate("window.__ORG.deptFail = false"); refresh(pg)
            check(count(pg) == "정상 2/4", f"복구 후 정상 2/4 (got {count(pg)})")

            print("8. 기존 기능 회귀")
            pg.click(f"{BASE_TAB} .ws-name"); pg.wait_for_timeout(200)
            check(pg.evaluate(f"document.querySelector('{BASE_TAB} .ws-approve-badge')?.textContent") == "⚠2",
                  "승인 대기 배지(활성 탭) 유지")
            pg.dblclick(f"{BASE_TAB} .ws-name"); pg.wait_for_timeout(100)
            check(pg.evaluate(f"document.querySelector('{BASE_TAB} .ws-name').isContentEditable"), "더블클릭 = 이름 변경 편집 진입")
            pg.keyboard.press("Escape"); pg.keyboard.press("Enter"); pg.wait_for_timeout(150)
            check(pg.inner_text(f"{BASE_TAB} .ws-name") == "non title", "이름 변경 확정 후 이름 보존")
            check(pg.evaluate("document.querySelectorAll('#ws-tabs .ws-tab').length") == 2, "탭 2개 유지")
            check(not errs, f"콘솔 pageerror 0건 (got {errs})")
            b.close()
    finally:
        httpd.shutdown()
    print(f"\n{'PASS' if not failures else 'FAIL'} — 실패 {len(failures)}건")
    for f in failures:
        print(f"  ✗ {f}")
    return 1 if failures else 0

if __name__ == "__main__":
    sys.exit(main())
