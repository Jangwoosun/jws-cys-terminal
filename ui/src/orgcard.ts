// 사이드바 부서 카드(조직도) — 노드 상태 분류·직책·진행률의 순수부.
//
// 입력은 데몬 org.status 응답(refreshSidebarStatus 가 nodeSig 로 캐싱)뿐이다. 상태를 추정하지
// 않는다: 데몬이 준 필드(exited·agent_alive·gate_pending·status.state·awakened_at·ctx)만으로
// 5색을 가른다. main.ts 는 이 결과를 DOM 으로 옮기기만 한다(orgcard.test.ts 가 박제).

/** 카드가 쓰는 노드 신호 — org.status surfaces[] 항목에서 필요한 필드만 옮긴 것. */
export type OrgNodeSig = {
  role: string | null;
  exited: boolean | null;
  agent_alive: boolean | null;
  /** gate_pending.gate — "gate_pending"(첫기동 관문 상주) · "gate_pending_stale"(낡은 표식) · null */
  gate: string | null;
  /** status.state 자기보고 — working | waiting | blocked | done · 미보고면 null */
  state: string | null;
  task: string | null;
  /** status.age_secs — 자기보고가 몇 초 전인가 */
  status_age: number | null;
  awakened: boolean;
  ctx_pct: number | null;
};

/** 5색 — 초록(작업)·파랑(대기)·노랑(시작·복구)·주황(확인 필요)·회색(종료·끊김). */
export type OrgTone = "working" | "waiting" | "starting" | "attention" | "down";

export const CTX_ATTENTION_PCT = 80;

/** 데몬 신호 → 색·상태 라벨. sig 가 없으면(조회 전·데몬 부재) 끊김으로 본다 — 없는 신호를 정상으로 칠하지 않는다. */
export function classifyNode(sig: OrgNodeSig | undefined): { tone: OrgTone; label: string } {
  if (!sig) return { tone: "down", label: "연결 끊김" };
  if (sig.exited === true) return { tone: "down", label: "종료" };
  if (sig.agent_alive === false) return { tone: "down", label: "연결 끊김" };
  if (sig.gate === "gate_pending") return { tone: "starting", label: "시작 관문 대기" };
  if (sig.gate === "gate_pending_stale") return { tone: "attention", label: "확인 필요(관문 표식)" };
  if (sig.state === "blocked") return { tone: "attention", label: "막힘" };
  if (sig.ctx_pct != null && sig.ctx_pct >= CTX_ATTENTION_PCT)
    return { tone: "attention", label: `컨텍스트 ${sig.ctx_pct}%` };
  if (sig.state === "working") return { tone: "working", label: "작업 중" };
  if (sig.state === "waiting") return { tone: "waiting", label: "대기 중" };
  if (sig.state === "done") return { tone: "waiting", label: "완료·대기" };
  if (!sig.awakened) return { tone: "starting", label: "각성 미확인" };
  return { tone: "attention", label: "상태 미보고" };
}

/** 정상 = 초록·파랑. 접힌 카드의 "정상 3/4" 집계. */
export function isHealthy(t: OrgTone): boolean {
  return t === "working" || t === "waiting";
}

/** 내부 역할명 — reviewer-codex·reviewer-claude-1 등은 reviewer 로 접는다. */
export function roleFamily(role: string | null): string {
  if (!role) return "node";
  if (role.startsWith("reviewer")) return "reviewer";
  return role;
}

/** 역할 표시 태그 — CSO 만 대문자(사용자 명세 표기). */
export function roleTag(role: string | null): string {
  const f = roleFamily(role);
  return f === "cso" ? "CSO" : f;
}

/** 부서별 한글 직책 — 키 = 부서 소켓 접미(부서 ID 불변이라 rename 에도 유지). */
export const ORG_TITLES: Record<string, Record<string, string>> = {
  "cys-dept-dept-1": {
    master: "한우리 교육연구부장",
    cso: "교육과정 운영실장",
    worker: "독서토론논술 수업연구원",
    reviewer: "수업·교재 품질검토관",
  },
};

const DEFAULT_TITLES: Record<string, string> = {
  ceo: "CEO",
  master: "마스터",
  cso: "CSO",
  worker: "워커",
  reviewer: "리뷰어",
};

export function titleFor(socket: string | null | undefined, role: string | null): string {
  const f = roleFamily(role);
  const key = (socket ?? "").split("\\").pop()?.split("/").pop() ?? "";
  return ORG_TITLES[key]?.[f] ?? DEFAULT_TITLES[f] ?? f;
}

/** org.status todo 맵 값 — verdict="counted" 이고 owner 가 선언된 파일만 진행률의 근거다. */
export type TodoEntry = { owner?: string; done?: number; total?: number; verdict?: string };

/** 역할의 진행률(%) — 귀속(counted) TODO 가 없으면 null(추정 금지 · 표시 생략). */
export function progressFor(todo: Record<string, TodoEntry> | undefined, role: string | null): number | null {
  if (!todo || !role) return null;
  let done = 0;
  let total = 0;
  for (const e of Object.values(todo)) {
    if (e.verdict !== "counted" || !e.owner) continue;
    if (!(e.owner === role || role.startsWith(`${e.owner}-`))) continue;
    done += e.done ?? 0;
    total += e.total ?? 0;
  }
  return total > 0 ? Math.round((done / total) * 100) : null;
}

/** 역할 표시 순서 — 부장이 맨 위, 그다음 CSO·워커·리뷰어. */
const ROLE_ORDER = ["ceo", "master", "cso", "worker", "reviewer"];
export function roleRank(role: string | null): number {
  const i = ROLE_ORDER.indexOf(roleFamily(role));
  return i < 0 ? ROLE_ORDER.length : i;
}

/** 자기보고 나이 → "3분 전"·"2시간 전". */
export function ageText(secs: number | null): string {
  if (secs == null) return "";
  if (secs < 60) return "방금";
  if (secs < 3600) return `${Math.floor(secs / 60)}분 전`;
  if (secs < 86400) return `${Math.floor(secs / 3600)}시간 전`;
  return `${Math.floor(secs / 86400)}일 전`;
}
