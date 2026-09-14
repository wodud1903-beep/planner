// 숫자·날짜 다루기 — planner/sheets.py 의 같은 이름 함수들을 옮긴 것.
// 각 규칙 뒤의 설명은 파이썬 쪽에 적힌 '과거에 실제로 났던 사고' 다. 그대로 지킨다.

// '₩57,035,000' → '57035000'
//   '₩1,234.56' → '1235'   (점을 그냥 지우면 123456, 즉 100배가 된다)
//   '₩-1,000'   → '-1000'
//   '(₩1,000)'  → '-1000'  (회계 표기의 괄호 = 음수)
export function digitsOnly(s) {
  let t = (s || "").trim();
  if (!t) return "";
  let neg = false;
  if (t.startsWith("(") && t.endsWith(")")) { neg = true; t = t.slice(1, -1); }
  if (t.includes("-")) neg = true;
  let kept = "";
  for (const ch of t) {
    // ⚠️ 파이썬 str.isdigit() 은 전각 숫자('３')도 참이고 float('３') 도 된다.
    //    한글 자판으로 친 값이 시트에 들어올 수 있어서 같이 받아 준다.
    const code = ch.codePointAt(0);
    if (code >= 0xff10 && code <= 0xff19) kept += String.fromCharCode(code - 0xff10 + 48);
    else if ((ch >= "0" && ch <= "9") || ch === ".") kept += ch;
  }
  if (!kept.split(".").join("")) return "";
  // ⚠️ parseFloat 은 앞부분만 읽어서 '1.234.567' 을 1.234 로 본다. 파이썬 float() 는
  //    거기서 오류를 내고 우리는 빈 값을 돌려준다. 그래서 통째로 숫자인지 먼저 본다.
  const f = Number(kept);
  if (!isFinite(f)) return "";
  // 파이썬 round() 는 짝수로 반올림하지만, 여기 쓰이는 값은 돈이라 .5 가 사실상
  // 안 나온다. 그래도 파이썬과 맞추려고 half-even 을 흉내 낸다.
  let n = Math.round(f);
  if (Math.abs(f % 1) === 0.5) {
    const down = Math.floor(f);
    n = (down % 2 === 0) ? down : down + 1;
  }
  if (n === 0) return "0";
  return (neg ? "-" : "") + String(n);
}

export function fmtMoney(s) {
  const d = digitsOnly(s);
  if (!d) return "";
  const neg = d.startsWith("-");
  const body = (neg ? d.slice(1) : d).replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  return (neg ? "-" : "") + body;
}

// '2026. 8. 14' / '2026-08-14' / '2026년 8월 14일' / '20260814' → Date. 못 읽으면 null.
// 못 읽는 형식을 '빈 값' 으로 오해하면 날짜가 지워지므로 넓게 받아들인다.
export function parseDate(s) {
  let t = (s || "").trim();
  if (!t) return null;
  t = t.split("T")[0].split(" 0:")[0].trim();
  const mk = (y, mo, d) => {
    y = parseInt(y, 10);
    if (y < 100) y += 2000;               // '26. 8. 14' → 2026
    mo = parseInt(mo, 10); d = parseInt(d, 10);
    if (!(mo >= 1 && mo <= 12) || !(d >= 1 && d <= 31)) return null;
    const dt = new Date(y, mo - 1, d);
    if (dt.getFullYear() !== y || dt.getMonth() !== mo - 1 || dt.getDate() !== d) {
      return null;                        // 2월 30일 같은 것
    }
    return dt;
  };
  let m = t.match(/^(\d{2,4})\s*[.\-/]\s*(\d{1,2})\s*[.\-/]\s*(\d{1,2})\s*\.?$/);
  if (m) return mk(m[1], m[2], m[3]);
  m = t.match(/^(\d{2,4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일?$/);
  if (m) return mk(m[1], m[2], m[3]);
  m = t.match(/^(\d{4})(\d{2})(\d{2})$/);
  if (m) return mk(m[1], m[2], m[3]);
  return null;
}

export function fmtDate(d) {
  if (!d) return "";
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

// 자유롭게 쓴 계약조건에서 개월 수를 뽑는다. 1~120 으로 가둔다.
// 표기가 없거나 범위를 벗어나면 **null** 이다(0 이 아니다) — 파이썬과 같다.
// 그 고객은 만기 계산에서 빠진다. 0 으로 두면 '0개월 계약' 처럼 취급될 수 있다.
export function contractMonths(terms) {
  const t = (terms || "").trim();
  if (!t) return null;
  const m = t.match(/(\d{1,3})\s*개\s*월/);
  if (!m) return null;
  const n = parseInt(m[1], 10);
  return (n >= 1 && n <= 120) ? n : null;
}
