// orgcard.ts 순수부 회귀 테스트 (bun test — 신규 의존성 0).
//
// 부서 카드가 데몬 신호만으로 5색을 가르고(추정 금지), 직책·진행률·정렬이 결정론인지 박제한다.
// 픽스처 형상은 2026-09-24 dept-1 org.status 실측(좌석 4·surface 4~7)에서 옮겼다.
import { describe, it, expect } from "bun:test";
import {
  classifyNode,
  isHealthy,
  roleFamily,
  roleTag,
  titleFor,
  progressFor,
  roleRank,
  ageText,
  type OrgNodeSig,
} from "./orgcard";

const base: OrgNodeSig = {
  role: "worker",
  exited: false,
  agent_alive: true,
  gate: null,
  state: "waiting",
  task: null,
  status_age: 30,
  awakened: true,
  ctx_pct: 5,
};
const sig = (p: Partial<OrgNodeSig>): OrgNodeSig => ({ ...base, ...p });
const DEPT = "\\\\.\\pipe\\cys-dept-dept-1";

describe("classifyNode — 데몬 신호 → 5색", () => {
  it("신호 없음 = 연결 끊김(회색) — 없는 신호를 정상으로 칠하지 않는다", () => {
    expect(classifyNode(undefined)).toEqual({ tone: "down", label: "연결 끊김" });
  });
  it("exited·agent_alive=false = 회색", () => {
    expect(classifyNode(sig({ exited: true })).tone).toBe("down");
    expect(classifyNode(sig({ agent_alive: false })).tone).toBe("down");
  });
  it("종료가 다른 모든 신호보다 우선", () => {
    expect(classifyNode(sig({ exited: true, state: "working", gate: "gate_pending" })).label).toBe("종료");
  });
  it("첫기동 관문 상주 = 노랑", () => {
    expect(classifyNode(sig({ gate: "gate_pending" })).tone).toBe("starting");
  });
  it("낡은 관문 표식 = 주황(확인 필요) — 자기보고 waiting 보다 우선", () => {
    const r = classifyNode(sig({ gate: "gate_pending_stale", state: "waiting" }));
    expect(r.tone).toBe("attention");
  });
  it("blocked = 주황", () => {
    expect(classifyNode(sig({ state: "blocked" })).tone).toBe("attention");
  });
  it("컨텍스트 80% 이상 = 주황, 79% 는 자기보고 그대로", () => {
    expect(classifyNode(sig({ state: "working", ctx_pct: 80 })).tone).toBe("attention");
    expect(classifyNode(sig({ state: "working", ctx_pct: 79 })).tone).toBe("working");
  });
  it("working = 초록 · waiting·done = 파랑", () => {
    expect(classifyNode(sig({ state: "working" })).tone).toBe("working");
    expect(classifyNode(sig({ state: "waiting" })).tone).toBe("waiting");
    expect(classifyNode(sig({ state: "done" })).tone).toBe("waiting");
  });
  it("자기보고 없음 + 각성 미확인 = 노랑 (reviewer-codex 실측 형상)", () => {
    const r = classifyNode(sig({ role: "reviewer-codex", state: null, awakened: false, ctx_pct: null }));
    expect(r).toEqual({ tone: "starting", label: "각성 미확인" });
  });
  it("자기보고 없음 + 각성 확인 = 주황(상태 미보고)", () => {
    expect(classifyNode(sig({ state: null, awakened: true })).label).toBe("상태 미보고");
  });
  it("알 수 없는 state 문자열은 정상으로 칠하지 않는다", () => {
    expect(isHealthy(classifyNode(sig({ state: "weird" })).tone)).toBe(false);
  });
});

describe("isHealthy — 정상 n/m 집계", () => {
  it("초록·파랑만 정상", () => {
    expect(isHealthy("working")).toBe(true);
    expect(isHealthy("waiting")).toBe(true);
    expect(isHealthy("starting")).toBe(false);
    expect(isHealthy("attention")).toBe(false);
    expect(isHealthy("down")).toBe(false);
  });
});

describe("역할명·직책", () => {
  it("reviewer-* 는 reviewer 로 접는다", () => {
    expect(roleFamily("reviewer-codex")).toBe("reviewer");
    expect(roleFamily("reviewer-claude-1")).toBe("reviewer");
    expect(roleFamily(null)).toBe("node");
  });
  it("태그는 CSO 만 대문자", () => {
    expect(roleTag("cso")).toBe("CSO");
    expect(roleTag("master")).toBe("master");
    expect(roleTag("reviewer-codex")).toBe("reviewer");
  });
  it("dept-1 소켓 = 한우리 직책 4종", () => {
    expect(titleFor(DEPT, "master")).toBe("한우리 교육연구부장");
    expect(titleFor(DEPT, "cso")).toBe("교육과정 운영실장");
    expect(titleFor(DEPT, "worker")).toBe("독서토론논술 수업연구원");
    expect(titleFor(DEPT, "reviewer-codex")).toBe("수업·교재 품질검토관");
  });
  it("unix 소켓 경로 접미도 같은 키로 해석", () => {
    expect(titleFor("/home/u/.local/state/cys-dept-dept-1", "master")).toBe("한우리 교육연구부장");
  });
  it("다른 부서·기본 데몬은 기본 직책", () => {
    expect(titleFor(undefined, "master")).toBe("마스터");
    expect(titleFor("\\\\.\\pipe\\cys-dept-dept-2", "cso")).toBe("CSO");
    expect(titleFor(undefined, "ceo")).toBe("CEO");
  });
  it("표시 순서: 부장 → CSO → 워커 → 리뷰어 → 기타", () => {
    const roles = ["reviewer-codex", "worker", "cso", "master", "x"];
    expect([...roles].sort((a, b) => roleRank(a) - roleRank(b))).toEqual([
      "master",
      "cso",
      "worker",
      "reviewer-codex",
      "x",
    ]);
  });
});

describe("progressFor — 귀속 TODO 만 진행률 근거", () => {
  const todo = {
    "C:\\a\\CSO_TODO.md": { owner: "cso", done: 20, total: 32, verdict: "counted" },
    "C:\\a\\MASTER_TODO.md": { done: 0, total: 1, verdict: "unclaimed" },
    "C:\\a\\REVIEWER_TODO.md": { owner: "reviewer", done: 1, total: 4, verdict: "counted" },
  };
  it("counted + owner 일치 = 반올림 %", () => {
    expect(progressFor(todo, "cso")).toBe(63); // 20/32 = 62.5
  });
  it("unclaimed 는 쓰지 않는다(추정 금지 → null)", () => {
    expect(progressFor(todo, "master")).toBeNull();
  });
  it("reviewer-codex 는 owner=reviewer 파일에 귀속", () => {
    expect(progressFor(todo, "reviewer-codex")).toBe(25);
  });
  it("todo 부재·역할 부재 = null", () => {
    expect(progressFor(undefined, "cso")).toBeNull();
    expect(progressFor(todo, null)).toBeNull();
  });
  it("total 0 은 null(0% 로 오표시 금지)", () => {
    expect(progressFor({ f: { owner: "worker", done: 0, total: 0, verdict: "counted" } }, "worker")).toBeNull();
  });
});

describe("ageText", () => {
  it("구간별 표기", () => {
    expect(ageText(null)).toBe("");
    expect(ageText(10)).toBe("방금");
    expect(ageText(125)).toBe("2분 전");
    expect(ageText(27758)).toBe("7시간 전");
    expect(ageText(200000)).toBe("2일 전");
  });
});
