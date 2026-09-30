#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_phoenix_reinject_dedup_2026_09_30.py — phoenix reinject 재발방지 회귀 핀(리포 커밋).

오너 예외 승인 티켓(2026-09-30 · custom-2026-09-30-restore-reinject)의 성공 기준 6개 시나리오를
가짜(fake) `cys()`(서브프로세스 대체 — 기존 test_phoenix_f1_production_path.py 등과 같은 관례)로
결정론 검증한다. 실 cys.exe·실 소켓·실 화면 접촉 0.

근거가 된 root cause(마스터 위임 티켓):
  ① javis_phoenix.py stage_reinject(6s)·stage_g2_ack(4s) 가 둘 다 `cys reinject --check` 를 불러
     ACK 미수신 시 각각 폴백 전문을 주입해 좌석당 재주입이 중복됐다.
  ② dept worker 주입은 acl_denied(external→worker)로 실패했는데 구분 없이 일반 fail 로 처리됐다.
  ③ codex 는 2차 재주입 붙여넣기가 미제출로 남았다. ★2026-10-01 오너 최종 지시로 A안 보강(화면
     기반 입력줄 안전판정)은 철회됐다 — codex 좌석은 phoenix 복원 경로에서 자동 재주입·추가 Return
     을 아예 하지 않고 ACK 미수신 시 manual_check_required 만 기록한다. codex 제출 보호 자체는
     별도 티켓으로 분리됐다(이 파일의 시나리오⑥은 '아무것도 안 한다'만 검증한다).
  ④ 빈 셸(agent 없음)은 'ok'로 조용히 skip 돼 실패가 저널·보고에 드러나지 않았다.

실행: python3 cysjavis-pack/bin/tests/test_phoenix_reinject_dedup_2026_09_30.py  (0=전건 PASS)
"""
import importlib.util
import os
import sys
from types import SimpleNamespace

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
PH = os.path.normpath(os.path.join(HERE, "..", "javis_phoenix.py"))
spec = importlib.util.spec_from_file_location("javis_phoenix", PH)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

_results = []


def check(name, cond, detail=""):
    _results.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + name + (" | " + detail if detail and not cond else ""))


def _R(rc=0, out="", err=""):
    return SimpleNamespace(returncode=rc, stdout=out, stderr=err)


def _status_row(agent="claude", agent_alive=True, exited=False):
    return {"surface_id": 7, "surface_ref": "surface:7", "role": "worker-1", "exited": exited,
            "agent_alive": agent_alive, "seat": "occupied", "agent": agent,
            "gate_pending": None, "registered_session_id": "s1"}


def _status_stdout(row):
    import json
    return json.dumps({"daemon": {"started_at": 0}, "surfaces": [row] if row else []})


# ── ①+② 중복 재주입 방지 + 늦은 ACK(1차 핑에서 이미 ack면 주입 0회) ──────────────────────────────
def scenario_1_no_duplicate_injection_on_ack():
    calls = []

    def fake_cys(*args, socket=None, timeout=25):
        calls.append(args)
        verb = args[0]
        if verb == "status":
            return _R(0, _status_stdout(_status_row()))
        if verb == "reinject" and "--check" in args:
            check("① ping 은 --no-inject 를 동반한다(주입 분리)", "--no-inject" in args, repr(args))
            return _R(0, "디렉티브 생존 확인 (ACK 수신) — 재주입 불필요")
        raise AssertionError("unexpected cys call in ack scenario: %r" % (args,))

    orig = m.cys
    m.cys = fake_cys
    try:
        j = {"roles": {}}
        ok, ev = m.stage_reinject("sock", "worker-1", "surface:7", False, j, ticket="t1")
        check("① ACK 즉시 → 성공", ok, ev)
        check("① ACK 즉시 → 폴백 전문 주입 0회(kind=ack 뿐)", not any(
            c[0] == "reinject" and "--check" not in c for c in calls), str(calls))
        ok2, ev2 = m.stage_g2_ack("sock", "worker-1", "surface:7", False, j)
        check("① g2 도 --no-inject 로만 핑한다", ok2 and "--no-inject" in calls[-1], str(calls[-1]))
        # 총 reinject 호출 2회(1차 핑 + g2 핑) 모두 --check --no-inject 뿐, 폴백 주입 호출은 없다.
        reinject_calls = [c for c in calls if c[0] == "reinject"]
        check("① reinject 호출은 정확히 2회(1차+g2), 전부 --check", len(reinject_calls) == 2
              and all("--check" in c for c in reinject_calls), str(reinject_calls))
    finally:
        m.cys = orig


def scenario_1b_timeout_then_single_forced_injection():
    """진짜 시간초과(ACK 없음·사용량제한 아님·ACL 아님·agent 있음) → 폴백 주입은 **정확히 1회**만."""
    calls = []
    injected_count = {"n": 0}

    def fake_cys(*args, socket=None, timeout=25):
        calls.append(args)
        verb = args[0]
        if verb == "status":
            return _R(0, _status_stdout(_status_row()))
        if verb == "read-screen":
            return _R(0, "bypass permissions on")  # 사용량 제한 문면 없음
        if verb == "reinject" and "--check" in args and "--no-inject" in args:
            return _R(0, "각성 핑 무응답 — no-inject 모드(주입 생략) (45s) surface:7")
        if verb == "reinject" and "--check" not in args:
            injected_count["n"] += 1
            return _R(0, "reinjected 42 bytes → surface:7 (worker-1) directive_sha256=" + ("a" * 64))
        raise AssertionError("unexpected cys call in timeout scenario: %r" % (args,))

    orig = m.cys
    m.cys = fake_cys
    try:
        j = {"roles": {}}
        ok, ev = m.stage_reinject("sock", "worker-1", "surface:7", False, j, ticket="t1")
        check("①b 진짜 타임아웃 → 실제 주입 성공", ok, ev)
        check("①b 폴백 주입은 정확히 1회", injected_count["n"] == 1, str(injected_count))
        check("①b 전달됨(delivered) 저널 기록", j["roles"]["worker-1"].get("reinject_delivered") is True, str(j["roles"]))
        check("①b directive_sha256 저널 기록", j["roles"]["worker-1"].get("reinject_directive_sha256") == "a" * 64)
        # g2 는 이 실행에서 별도 호출되어도 --no-inject 뿐이라 추가 주입을 만들지 않는다.
        ok2, ev2 = m.stage_g2_ack("sock", "worker-1", "surface:7", False, j)
        check("①b g2 단계에서도 주입 카운트 불변(여전히 1)", injected_count["n"] == 1, str(injected_count))
    finally:
        m.cys = orig


# ── ③ ACL 거부 → 부서 master 위임 1회, 직접 재시도 없음 ─────────────────────────────────────────
def scenario_3_acl_denied_delegates_once():
    delegate_calls = []
    ping_calls = {"n": 0}

    def fake_cys(*args, socket=None, timeout=25):
        verb = args[0]
        if verb == "status":
            return _R(0, _status_stdout(_status_row()))
        if verb == "reinject" and "--check" in args:
            ping_calls["n"] += 1
            return _R(1, "", "error: acl_denied: acl denied: external → worker-1 (pack/acl.json)")
        if verb == "send" and "--queued" in args:
            delegate_calls.append(args)
            return _R(0, "QUEUED (depth 1)")
        raise AssertionError("unexpected cys call in acl scenario: %r" % (args,))

    orig = m.cys
    m.cys = fake_cys
    try:
        j = {"roles": {}}
        ok, ev = m.stage_reinject("sock", "worker-1", "surface:7", False, j, ticket="t1")
        check("③ ACL 거부는 실패가 아니라 위임으로 종결", ok and "acl_denied" in ev, ev)
        check("③ 위임 메시지 1회 발신", len(delegate_calls) == 1, str(delegate_calls))
        check("③ 위임 메시지가 --to master 로 감", delegate_calls and delegate_calls[0][
            delegate_calls[0].index("--to") + 1] == "master", str(delegate_calls))
        check("③ 저널에 acl_delegated=True 기록", j["roles"]["worker-1"].get("acl_delegated") is True)
        # 같은 실행 안에서 재호출(F-1 재관측 패스 모사) → 중복 위임 금지(dedup).
        ok2, ev2 = m.stage_reinject("sock", "worker-1", "surface:7", False, j, ticket="t1")
        check("③ 재호출해도 위임은 여전히 1회(dedup)", len(delegate_calls) == 1, str(delegate_calls))
        check("③ ACL 거부 뒤 직접 폴백 주입을 시도하지 않았다(reinject 호출은 --check 뿐)",
              ping_calls["n"] == 2, str(ping_calls))
    finally:
        m.cys = orig


# ── ④ 사용량 제한 화면 → 재주입 안 함(진짜 타임아웃과 구분) ─────────────────────────────────────
def scenario_4_rate_limited_screen_blocks_injection():
    calls = []

    def fake_cys(*args, socket=None, timeout=25):
        calls.append(args)
        verb = args[0]
        if verb == "status":
            return _R(0, _status_stdout(_status_row()))
        if verb == "reinject" and "--check" in args:
            return _R(0, "각성 핑 무응답 — no-inject 모드(주입 생략) (45s) surface:7")
        if verb == "read-screen":
            return _R(0, "Approaching rate limits / Switch to gpt-5.6-luna?")
        raise AssertionError("unexpected cys call(주입을 시도했다면 여기서 걸린다): %r" % (args,))

    orig = m.cys
    m.cys = fake_cys
    try:
        j = {"roles": {}}
        ok, ev = m.stage_reinject("sock", "worker-1", "surface:7", False, j, ticket="t1")
        check("④ 사용량 제한 감지 → 실패(재시도 대상)로 보류", not ok, ev)
        check("④ evidence 에 ratelimited 명시", "ratelimited" in ev, ev)
        check("④ delivered 플래그가 세워지지 않음(주입 안 함)",
              not j["roles"].get("worker-1", {}).get("reinject_delivered"), str(j["roles"]))
    finally:
        m.cys = orig


# ── ⑤ 빈 셸 → 실패로 드러남(조용한 skip 금지) ────────────────────────────────────────────────
def scenario_5_empty_shell_surfaced_not_silent():
    # 진짜 '빈 셸'(agent=None) 케이스 — 상태 행은 있으나 배정된 agent 가 없다.
    def fake_cys(*args, socket=None, timeout=25):
        verb = args[0]
        if verb == "status":
            return _R(0, _status_stdout(_status_row(agent=None)))
        raise AssertionError("빈 셸 스킵 뒤 추가 cys 호출이 있으면 안 된다: %r" % (args,))

    orig = m.cys
    m.cys = fake_cys
    try:
        j = {"roles": {}}
        ok, ev = m.stage_reinject("sock", "worker-1", "surface:7", False, j, ticket="t1")
        check("⑤ 빈 셸은 stage 자체는 done=True(무한 재시도 방지)", ok, ev)
        check("⑤ evidence 에 skip 사유가 남는다", "kind=skip" in ev, ev)
        status = m._reinject_jevent_status(ok, ev)
        check("⑤ jevent status 가 'ok' 로 뭉개지지 않고 skip_no_agent 로 구분된다",
              status == "skip_no_agent", status)
    finally:
        m.cys = orig


# ── ⑥ Codex 미제출: ACK 미수신 시 codex 좌석은 주입·Return 0회, manual_check_required 기록 ────────
# ★2026-10-01 오너 최종 지시로 직전 A안 보강(붙여넣기 안전판정) 지시는 철회됐다 — codex 는 phoenix
# 복원 경로에서 ①자동 재주입 ②추가 Return 을 아예 하지 않는다(read-screen 기반 입력줄 판정 코드
# 없음). 요구 6(codex 제출 보호)은 별도 티켓으로 분리됐다.
def scenario_6_codex_manual_check_required_on_noack():
    calls = []

    def fake_cys(*args, socket=None, timeout=25):
        calls.append(args)
        verb = args[0]
        if verb == "status":
            return _R(0, _status_stdout(_status_row(agent="codex")))
        if verb == "reinject" and "--check" in args:
            return _R(0, "각성 핑 무응답 — no-inject 모드(주입 생략) (45s) surface:7")
        if verb == "read-screen":
            return _R(0, "bypass permissions on")  # 사용량 제한 문면 없음 → 진짜 timeout 분류
        raise AssertionError(
            "codex 좌석은 ACK 미수신 시 주입·send·send-key 를 전혀 호출하면 안 된다: %r" % (args,))

    orig = m.cys
    m.cys = fake_cys
    try:
        j = {"roles": {}}
        ok, ev = m.stage_reinject("sock", "worker-1", "surface:7", False, j, ticket="t1")
        check("⑥ codex ACK 미수신 → 실패 아니라 확정된 상태(재시도 루프 없음)", ok, ev)
        check("⑥ evidence 에 manual_check_required 명시", "manual_check_required" in ev, ev)
        check("⑥ 저널에 reinject_manual_check_required=True 기록",
              j["roles"]["worker-1"].get("reinject_manual_check_required") is True, str(j["roles"]))
        check("⑥ delivered 플래그 없음(주입 안 함)",
              not j["roles"]["worker-1"].get("reinject_delivered"), str(j["roles"]))
        check("⑥ 폴백 주입(reinject --check 없는 호출) 0회",
              not any(c[0] == "reinject" and "--check" not in c for c in calls), str(calls))
        check("⑥ send/send-key 호출 0회(Return 도 전혀 보내지 않음)",
              not any(c[0] in ("send", "send-key") for c in calls), str(calls))
        status = m._reinject_jevent_status(ok, ev)
        check("⑥ jevent status 가 manual_check_required 로 구분된다", status == "manual_check_required", status)
    finally:
        m.cys = orig


def scenario_6b_codex_ack_short_circuits_before_manual_check():
    """대조군: codex 도 ACK 만 받으면(이미 살아있으면) manual_check_required 로 가지 않는다."""
    calls = []

    def fake_cys(*args, socket=None, timeout=25):
        calls.append(args)
        verb = args[0]
        if verb == "status":
            return _R(0, _status_stdout(_status_row(agent="codex")))
        if verb == "reinject" and "--check" in args:
            return _R(0, "디렉티브 생존 확인 (ACK 수신) — 재주입 불필요")
        raise AssertionError("ACK 수신 뒤 추가 cys 호출이 있으면 안 된다: %r" % (args,))

    orig = m.cys
    m.cys = fake_cys
    try:
        j = {"roles": {}}
        ok, ev = m.stage_reinject("sock", "worker-1", "surface:7", False, j, ticket="t1")
        check("⑥b codex ACK 수신 → 성공(manual_check_required 아님)", ok and "manual_check_required" not in ev, ev)
    finally:
        m.cys = orig


def main():
    scenario_1_no_duplicate_injection_on_ack()
    scenario_1b_timeout_then_single_forced_injection()
    scenario_3_acl_denied_delegates_once()
    scenario_4_rate_limited_screen_blocks_injection()
    scenario_5_empty_shell_surfaced_not_silent()
    scenario_6_codex_manual_check_required_on_noack()
    scenario_6b_codex_ack_short_circuits_before_manual_check()

    npass = sum(1 for c in _results if c)
    print("\n=== %d/%d PASS ===" % (npass, len(_results)))
    return 0 if npass == len(_results) else 1


if __name__ == "__main__":
    sys.exit(main())
