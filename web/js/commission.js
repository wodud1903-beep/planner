// 수당 계산 — planner/commission.py 의 계산식을 그대로 옮긴 것.
//
// ⚠️ 돈이 나오는 계산이다. 파이썬과 1원이라도 달라지면 안 된다.
//    web/verify/vectors.json 에 파이썬이 낸 정답표가 있고 검사가 대조한다.
import { digitsOnly } from "./fmt.js";

export const BRANDS = ["hyundai", "kia"];
export const BRAND_NAMES = { hyundai: "현대", kia: "기아" };

export const TAXFREE_DIV = 1.0533;   // 면세 → 과세 환산
export const TRUCK_DIV = 1.1;        // 화물차 공급가 환산
export const CAR_DIV = 1.1572;       // 승용차 공급가 환산
export const WITHHOLD = 0.967;       // 3.3% 원천공제
export const DEF_PAY_RATE = 70.0;    // 기본 지급율(%)

/** 최종 지급수수료(원). 소수점 이하는 버린다. */
export function calc(price, ratePct, isTruck, payRatePct = DEF_PAY_RATE, taxFree = false) {
  let p = Number(price);
  if (!isFinite(p)) p = 0;
  if (p <= 0) return 0;
  const adj = taxFree ? p / TAXFREE_DIV : p;
  const div = isTruck ? TRUCK_DIV : CAR_DIV;
  const val = (adj / div) * (Number(ratePct) / 100) * (Number(payRatePct) / 100) * WITHHOLD;
  // ⚠️ 파이썬 int() 는 0 쪽으로 자른다. Math.floor 가 아니라 Math.trunc 여야
  //    음수에서도 같아진다.
  return val > 0 ? Math.trunc(val) : 0;
}

/** 사람이 친 차량가에서 숫자만 — "5,200만" 같은 건 받지 않는다(파이썬과 같다). */
export const priceOf = (s) => Number(digitsOnly(s) || 0);

const KO_BRAND = { "현대": "hyundai", "기아": "kia" };

/** 공유 수당율 탭(A1:D)을 푼다. sheets.py 의 read_rates 와 같은 규칙.
 *  둘 다 비면 null — '아직 아무도 안 올린 상태' 다. */
export function parseRates(rows) {
  const out = { hyundai: [], kia: [] };
  for (const row of rows || []) {
    if (!row || row.length < 3) continue;
    const brand = String(row[0] ?? "").trim();
    if (brand === "브랜드" || brand === "") continue;       // 머리글
    const key = KO_BRAND[brand] || brand.trim().toLowerCase();
    if (!(key in out)) continue;
    const name = String(row[1] ?? "").trim();
    if (!name) continue;
    const rate = parseFloat(String(row[2] ?? "").replace("%", "").trim());
    if (!isFinite(rate)) continue;
    const truck = row.length > 3
      && ["TRUE", "Y", "예", "1", "O"].includes(String(row[3] ?? "").trim().toUpperCase());
    out[key].push([name, rate, truck]);
  }
  return (out.hyundai.length || out.kia.length) ? out : null;
}
