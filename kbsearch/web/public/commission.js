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


// 기본 수당율 표 — 공용 시트를 못 읽을 때 쓴다.
//
// PC 앱은 시트가 없어도 프로그램에 든 이 표로 계산한다. 폰만 못 쓰면 안 되므로
// 같은 표를 여기에도 둔다. **시트를 읽으면 그쪽이 언제나 이긴다** —
// 이건 어디까지나 없을 때의 대비다.
//
// ⚠️ planner/commission.py 의 DEFAULT_RATES 와 한 줄도 달라선 안 된다.
//    정답표(vectors.json)에 파이썬 표가 들어 있고 검사가 통째로 대조한다.
export const DEFAULT_RATES = {
  hyundai: [
    ["아반떼 / HEV", 7, false],
    ["ST1", 3.7, true],
    ["아이오닉 5 / 6", 4, false],
    ["쏘나타 / HEV", 6, false],
    ["그랜저 가솔린", 5, false],
    ["그랜저 HEV", 4.8, false],
    ["신형 G90 3.5T", 3.5, false],
    ["신형 G90 3.5T LWB", 3.2, false],
    ["G80 ev", 3, false],
    ["G80", 4.3, false],
    ["G70 2.0 / 2.2", 4.6, false],
    ["GV70", 4.3, false],
    ["GV80", 4.1, false],
    ["아이오닉 9", 3.3, false],
    ["투싼", 5.5, false],
    ["베뉴", 6.8, false],
    ["넥쏘 수소", 2.3, false],
    ["코나 / 코나 HEV", 5.8, false],
    ["코나 EV", 4.2, false],
    ["싼타페", 5.3, false],
    ["싼타페 HEV", 5.1, false],
    ["팰리세이드", 4.8, false],
    ["팰리세이드 HEV", 4.6, false],
    ["GV70 ev", 3, false],
    ["GV60 ev", 3, false],
    ["포터", 7, true],
    ["포터 EV", 3.5, false],
    ["포터 캠핑카", 3.3, true],
    ["스타리아", 6, true],
    ["스타리아 라운지", 5.5, false],
    ["스타리아 카고 EV", 4, true],
    ["스타리아 투어러 EV", 3.8, true],
    ["스타리아 라운지 EV", 4, false],
    ["스타리아 리무진 EV", 3.3, false],
    ["스타리아 HEV", 5.3, true],
    ["쏠라티", 4, true],
    ["파비스", 3.6, true],
    ["카운티", 5, true],
    ["카운티 EV", 1.8, true],
    ["에어로타운", 5, true],
    ["유니버스", 3.5, true],
    ["마이티,메가트럭", 5, true],
  ],
  kia: [
    ["모닝", 7.5, false],
    ["레이", 7.5, false],
    ["레이EV(라이트)", 4.8, false],
    ["레이EV(에어)", 5, false],
    ["K3", 7, false],
    ["K5", 6, false],
    ["K5 HEV", 6, false],
    ["K8", 5, false],
    ["K9", 4.3, false],
    ["K9 (퀀텀)", 4, false],
    ["니로", 6, false],
    ["니로 EV", 5, false],
    ["셀토스", 5.5, false],
    ["EV6", 3.3, false],
    ["EV3", 4.2, false],
    ["카니발", 6, false],
    ["스포티지", 5.5, false],
    ["쏘렌토", 5.5, false],
    ["모하비", 5, false],
    ["봉고1톤", 7, true],
    ["봉고 1.2톤", 6, true],
    ["봉고 EV", 3.8, true],
    ["대형버스", 3, true],
    ["EV9_에어", 2.8, false],
    ["EV9_어스", 3.1, false],
    ["EV9_GT-line", 3.2, false],
    ["EV9_GT", 3.5, false],
    ["타스만", 5.5, true],
    ["EV4 / EV5", 4.2, false],
    ["PV5", 4.5, true],
  ],
};
