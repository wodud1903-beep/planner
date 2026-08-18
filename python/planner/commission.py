"""차량 수당(수수료) 계산 — 브랜드·차종별 수당율 표와 계산식.

계산식(웹 계산기에서 그대로 옮김)
  면세 차량이면 차량가를 1.0533 으로 나눠 과세 기준으로 맞춘다.
  화물차는 1.1, 승용차는 1.1572 로 나눈 공급가에
  차종 수당율 × 지급율(기본 70%) × 0.967(3.3% 공제) 을 곱한다.

수당율은 수시로 바뀌므로 설정에서 고칠 수 있게 파일로 보관한다.
"""

from __future__ import annotations

import json

from . import config

RATES_FILE = "commission_rates.json"
BRANDS = ("hyundai", "kia")
BRAND_NAMES = {"hyundai": "현대", "kia": "기아"}

TAXFREE_DIV = 1.0533      # 면세 → 과세 환산
TRUCK_DIV = 1.1           # 화물차 공급가 환산
CAR_DIV = 1.1572          # 승용차 공급가 환산
WITHHOLD = 0.967          # 3.3% 원천공제
DEF_PAY_RATE = 70.0       # 기본 지급율(%)

# (차종, 수당율, 화물여부)
DEFAULT_RATES: dict = {
    "hyundai": [
        ("아반떼 / HEV", 7.0, False), ("ST1", 3.7, True),
        ("아이오닉 5 / 6", 4.0, False), ("쏘나타 / HEV", 6.0, False),
        ("그랜저 가솔린", 5.0, False), ("그랜저 HEV", 4.8, False),
        ("신형 G90 3.5T", 3.5, False), ("신형 G90 3.5T LWB", 3.2, False),
        ("G80 ev", 3.0, False), ("G80", 4.3, False),
        ("G70 2.0 / 2.2", 4.6, False), ("GV70", 4.3, False),
        ("GV80", 4.1, False), ("아이오닉 9", 3.3, False),
        ("투싼", 5.5, False), ("베뉴", 6.8, False),
        ("넥쏘 수소", 2.3, False), ("코나 / 코나 HEV", 5.8, False),
        ("코나 EV", 4.2, False), ("싼타페", 5.3, False),
        ("싼타페 HEV", 5.1, False), ("팰리세이드", 4.8, False),
        ("팰리세이드 HEV", 4.6, False), ("GV70 ev", 3.0, False),
        ("GV60 ev", 3.0, False), ("포터", 7.0, True),
        ("포터 EV", 3.5, False), ("포터 캠핑카", 3.3, True),
        ("스타리아", 6.0, True), ("스타리아 라운지", 5.5, False),
        ("스타리아 카고 EV", 4.0, True), ("스타리아 투어러 EV", 3.8, True),
        ("스타리아 라운지 EV", 4.0, False), ("스타리아 리무진 EV", 3.3, False),
        ("스타리아 HEV", 5.3, True), ("쏠라티", 4.0, True),
        ("파비스", 3.6, True), ("카운티", 5.0, True),
        ("카운티 EV", 1.8, True), ("에어로타운", 5.0, True),
        ("유니버스", 3.5, True), ("마이티,메가트럭", 5.0, True),
    ],
    "kia": [
        ("모닝", 7.5, False), ("레이", 7.5, False),
        ("레이EV(라이트)", 4.8, False), ("레이EV(에어)", 5.0, False),
        ("K3", 7.0, False), ("K5", 6.0, False),
        ("K5 HEV", 6.0, False), ("K8", 5.0, False),
        ("K9", 4.3, False), ("K9 (퀀텀)", 4.0, False),
        ("니로", 6.0, False), ("니로 EV", 5.0, False),
        ("셀토스", 5.5, False), ("EV6", 3.3, False),
        ("EV3", 4.2, False), ("카니발", 6.0, False),
        ("스포티지", 5.5, False), ("쏘렌토", 5.5, False),
        ("모하비", 5.0, False), ("봉고1톤", 7.0, True),
        ("봉고 1.2톤", 6.0, True), ("봉고 EV", 3.8, True),
        ("대형버스", 3.0, True), ("EV9_에어", 2.8, False),
        ("EV9_어스", 3.1, False), ("EV9_GT-line", 3.2, False),
        ("EV9_GT", 3.5, False), ("타스만", 5.5, True),
        ("EV4 / EV5", 4.2, False), ("PV5", 4.5, True),
    ],
}


def default_rates() -> dict:
    """기본 수당율 표 (복사본)."""
    return {b: [tuple(x) for x in DEFAULT_RATES[b]] for b in BRANDS}


def load_rates() -> dict:
    """저장된 수당율. 없거나 깨졌으면 기본값."""
    try:
        p = config.data_file(RATES_FILE)
        if p.exists():
            o = json.loads(p.read_text(encoding="utf-8"))
            out = {}
            for b in BRANDS:
                items = []
                for row in (o.get(b) or []):
                    try:
                        name = str(row[0]).strip()
                        rate = float(row[1])
                        truck = bool(row[2])
                    except Exception:
                        continue
                    if name:
                        items.append((name, rate, truck))
                out[b] = items
            if any(out.get(b) for b in BRANDS):
                # 한쪽 브랜드만 비어 있으면 그쪽은 기본값으로 채운다
                for b in BRANDS:
                    if not out.get(b):
                        out[b] = [tuple(x) for x in DEFAULT_RATES[b]]
                return out
    except Exception:
        pass
    return default_rates()


def save_rates(rates: dict) -> None:
    try:
        data = {b: [[n, float(r), bool(t)] for n, r, t in (rates.get(b) or [])]
                for b in BRANDS}
        config.atomic_write(config.data_file(RATES_FILE),
                            json.dumps(data, ensure_ascii=False, indent=2))
    except Exception:
        pass


def calc(price: float, rate_pct: float, is_truck: bool,
         pay_rate_pct: float = DEF_PAY_RATE, tax_free: bool = False) -> int:
    """최종 지급수수료(원). 소수점 이하는 버린다."""
    try:
        price = float(price or 0)
    except Exception:
        price = 0.0
    if price <= 0:
        return 0
    adj = price / TAXFREE_DIV if tax_free else price
    div = TRUCK_DIV if is_truck else CAR_DIV
    val = (adj / div) * (float(rate_pct) / 100.0) \
        * (float(pay_rate_pct) / 100.0) * WITHHOLD
    return int(val) if val > 0 else 0
