"""자료검색함의 기본 자료.

실제로 쓰시는 심사서류 안내문과, 손으로 관리하시던 캐피탈별 승계조건표·
연락처표를 그대로 옮겨 둔 것이다. 자료만 모아 두는 파일이라 로직은 없다.
관리자가 [자료 편집] 에서 고치면 이 값은 더 이상 쓰이지 않는다
(캐시나 시트에 저장된 것이 먼저다).

두 원본에서 값이 어긋나던 곳은 아래 규칙으로 정리했다.
  · 승계부서 번호가 다른 7곳 → **연락처표 값**을 쓴다.
  · DGB캐피탈 = iM캐피탈, M캐피탈 = MG캐피탈 로 합쳤다.
  · 승계 가능여부·잔여일이 다른 두 곳(우리카드·SK렌터카)만 그 줄에 병기했다.
  · 우리카드 견적 사이트의 로그인 ID/PW 는 넣지 않았다 — 이 자료는 전 직원이
    보는 스프레드시트로 올라간다.
"""

from __future__ import annotations

CAT_DOCS = "심사서류"
CAT_COMPANY = "캐피탈"
CAT_CONTACT = "연락처"

FAX = "0504-214-5287"


# ---------------------------------------------------------------------------
# 심사서류 — 고객에게 그대로 보내는 안내문
# ---------------------------------------------------------------------------
DOCS = [
    {
        "category": CAT_DOCS, "finance": "", "title": "개인 심사서류",
        "tags": "개인 직장인 급여소득자 면허증 건강보험",
        "body": (
            "1. 면허증\n"
            "2. 건강보험자격득실확인서\n"
            "3. 건강보험 납부확인서\n"
            f"팩스- {FAX}\n"
            "\n"
            "사진 또는 팩스로 보내주시면 됩니다\n"
            "\n"
            "\n"
            "#건강보험자격득실&납부확인서 발급방법#\n"
            "\n"
            "건강보험공단 고객센터\n"
            "1577-1000\n"
            "\n"
            "ARS 연결하여 제 팩스번호 입력 후, 두가지 서류 발급요청 드립니다.\n"
            "발급은 최근 1년으로 부탁드리겠습니다 ^^*\n"
            f"팩스번호 : {FAX}\n"
            "\n"
            "발급 번거로우시면 카톡 간편인증 보내드리고 제가 바로 발급 가능하오니, "
            "어려우시면 말씀 부탁드리겠습니다."
        ),
        "checklist": ["면허증", "건강보험자격득실확인서", "건강보험 납부확인서"],
    },
    {
        "category": CAT_DOCS, "finance": "", "title": "개인사업자 심사서류",
        "tags": "사업자 개인사업자 부가세 부가가치세",
        "body": (
            "1. 면허증\n"
            "2. 사업자등록증\n"
            "3. 부가가치세 표준증명원 25/26년도\n"
            "\n"
            "\n"
            "카톡 또는 팩스 편하신쪽으로 부탁드리겠습니다.\n"
            f"Fax.{FAX}\n"
            "\n"
            "부가세자료는 발급 번거로우시면 카톡 간편인증 보내드리고 제가 바로 "
            "발급 가능하오니, 어려우시면 말씀 부탁드리겠습니다."
        ),
        "checklist": ["면허증", "사업자등록증", "부가가치세 표준증명원 25/26년도"],
    },
    {
        "category": CAT_DOCS, "finance": "", "title": "법인 심사서류",
        "tags": "법인 재무제표 주주명부 등기부등본",
        "body": (
            "1. 대표자님 신분증/연락처\n"
            "2. 사업자등록증\n"
            "3. 부가가치세 표준증명원 24/25/26년도\n"
            "4. 법인 재무제표 24/25년도\n"
            "5. 주주명부\n"
            "6. 등기부등본 (말소사항 포함)\n"
            "\n"
            "\n"
            "팩스 또는 카톡 편하신쪽으로 회신 부탁드리겠습니다.\n"
            f"Fax.{FAX}"
        ),
        "checklist": [
            "대표자님 신분증/연락처", "사업자등록증",
            "부가가치세 표준증명원 24/25/26년도", "법인 재무제표 24/25년도",
            "주주명부", "등기부등본 (말소사항 포함)",
        ],
    },
]


# ---------------------------------------------------------------------------
# 캐피탈·렌터카 — 승계조건표 + 조건표/연락처를 한 장으로
# ---------------------------------------------------------------------------
def _company(name, tags="", succ=None, econtract="", corpdoc="", driver="",
             web="", call="", accident="", takeover="") -> dict:
    """회사 한 곳의 자료를 만든다. 값이 없는 항목은 아예 넣지 않는다.

    빈 칸에 '-' 를 적어 두면 화면에서 읽을 게 늘기만 하고 도움이 안 된다.
    """
    parts = []
    if succ:
        lines = ["■ 승계 조건"]
        for label, key in (("최소 납부횟수", "pay"),
                           ("만기 최소 잔여일", "left"),
                           ("매매상사(완납승계)", "resale"),
                           ("승계 수수료", "fee")):
            if succ.get(key):
                lines.append(f"· {label} : {succ[key]}")
        if succ.get("note"):
            lines.append(f"· {succ['note']}")
        parts.append("\n".join(lines))
    for cap, val in (("■ 전자약정 필요정보", econtract),
                     ("■ 법인약정 필요서류", corpdoc),
                     ("■ 운전자 범위", driver),
                     ("■ 견적 홈페이지", web)):
        if val:
            parts.append(cap + "\n" + val)
    nums = [(lbl, v) for lbl, v in (("콜센터", call), ("사고처리", accident),
                                    ("승계부서", takeover)) if v]
    if nums:
        parts.append("■ 연락처\n" + "\n".join(f"· {lbl} : {v}" for lbl, v in nums))
    return {
        "category": CAT_COMPANY, "finance": name, "title": name,
        "tags": (tags + " 승계 전자약정 법인약정 연락처 조건표").strip(),
        "body": "\n\n".join(parts),
        "checklist": [],
    }


COMPANIES = [
    _company(
        "현대캐피탈", "현캐",
        succ={"pay": "1회", "left": "3개월", "resale": "가능",
              "fee": "미회수 원금 1%"},
        econtract="실행요청서 / 연대보증서 / 인도주소",
        corpdoc="연대보증인 계약서",
        driver="나이제한 없음",
        web="단톡방 담당자 통해서 진행",
        call="1588-2114", accident="1588-2114", takeover="1588-2114"),

    _company(
        "롯데렌터카", "롯데렌탈 롯렌",
        succ={"pay": "1회", "left": "45일", "resale": "불가",
              "fee": "165,000원 ~ 550,000원"},
        econtract="1. 이메일 주소\n2. 결제일\n3. 자동이체 계좌번호\n"
                  "4. 인도지 주소\n5. 인도 희망일",
        corpdoc="법인 전자약정 가능",
        driver="만 74세 미만\n누구나운전 보험 가능(월2만원, 롯데 단독)",
        web="PC : https://epartner.lotterental.net/\n모바일 접속불가",
        call="1588-1230", accident="1588-1230", takeover="1588-1230"),

    _company(
        "SK렌터카", "에스케이렌터카",
        succ={"pay": "1회", "left": "1개월  (연락처표에는 2개월로 적혀 있음)",
              "resale": "불가", "fee": "330,000원"},
        call="1599-9111", accident="1599-9111", takeover="1577-2280"),

    _company(
        "롯데캐피탈", "롯캐",
        succ={"pay": "3회", "left": "2개월", "resale": "불가", "fee": "330,000원"},
        econtract="1. 이메일 주소\n2. 결제일\n3. 자동이체 계좌번호\n4. 차량 인도지",
        corpdoc="근보증서 + 필수동의서 + 개인인감날인or서명",
        driver="개시일(계약시점) 기준 만 75세까지 운전가능\n"
               "계약 후 5년 뒤 만 80세까지 운전 가능",
        web="PC : https://auto.lottecap.com/lg\n모바일 접속불가",
        call="1577-7700", accident="1588-4800", takeover="1577-7700"),

    _company(
        "MG캐피탈", "엠지캐피탈 M캐피탈",
        succ={"pay": "3회~6회 후", "left": "2개월", "resale": "불가",
              "fee": "500,000원 ~ 700,000원"},
        econtract="카카오페이 가입 필수\n1. 등본\n2. 자동이체 통장사본\n"
                  "3. 이메일주소\n4. 결제일자 (1, 5, 10, 15, 20, 25) 택1\n"
                  "5. 모집인확인서 / 펀딩요청서 (리스)",
        corpdoc="법인 전자약정 불가, 지류약정",
        driver="개시일 기준 만 69세까지 계약가능",
        web="별도 홈페이지 없음, 엑셀견적기",
        call="1588-9688", accident="1644-1199", takeover="1588-9688"),

    _company(
        "iM캐피탈", "아이엠캐피탈 DGB캐피탈 디지비",
        succ={"pay": "3회", "left": "1개월", "resale": "가능",
              "fee": "550,000원 ~ 1,000,000원"},
        econtract="배송주소 / 썬팅농도",
        corpdoc="근보증서 / 실행요청서 / 매매계약서 / 법인인감증명서",
        driver="만 26~70세 진행 가능",
        web="PC : https://www.imcap.co.kr/admin/dgbLogin.do\n"
            "모바일 : iM캐피탈 파트너 앱 다운로드\n"
            "- iOS : https://myip.kr/rhCgJ\n"
            "- 안드로이드 : https://myip.kr/suyxd",
        call="1566-0050", accident="1577-0565", takeover="1566-8808"),

    _company(
        "아마존카", "아마존",
        succ={"left": "1개월", "resale": "불가"},
        econtract="통장사본 / 대리점 담당자 명함",
        corpdoc="대표자 신분증 / 자동이체통장 / 주운전자면허증 사본",
        driver="만 69세까지 운전가능",
        web="PC / 모바일 : https://www.amazoncar.co.kr/",
        call="02-392-4242", accident="1588-6688", takeover="1588-5211"),

    _company(
        "JB우리캐피탈", "제이비 전북",
        succ={"pay": "6회", "left": "1개월", "resale": "불가", "fee": "330,000원"},
        econtract="별도 정보 없이 전자약정 진행",
        corpdoc="근보증서 + 법인인감날인",
        web="PC/모바일 : https://emp.wooricap.com/",
        call="1688-2300", accident="1666-8800", takeover="02-6222-7957"),

    _company(
        "메리츠캐피탈", "메리츠",
        succ={"pay": "1회", "left": "1개월", "resale": "가능",
              "fee": "300,000원 ~ 1,000,000원",
              "note": "정산일 : 완납일 기준 / 이전서류 바로 발송가능 "
                      "(기간유지 없음) / 승계 후 완납"},
        econtract="1. 통신사\n2. 자택주소\n3. 납입일자 (1,5,10,15,20,25,말일)\n"
                  "4. 이메일\n5. 계좌번호",
        corpdoc="법인 지류약정",
        driver="만 70세까지 운전가능",
        web="별도 홈페이지 없음 / 엑셀견적기",
        call="1588-9666", accident="1577-0565", takeover="02-3462-6600"),

    _company(
        "우리금융캐피탈", "우리금융 우캐",
        succ={"pay": "1회", "left": "6개월", "resale": "가능",
              "fee": "300,000원 ~ 1,000,000원"},
        econtract="1. 결제일자(2,8,14,20) 택 1\n2. 자동이체 계좌번호\n"
                  "3. 이메일\n4. 주소",
        corpdoc="연대보증 계약서 / 인감증명서",
        driver="종료시점 만 75세까지",
        web="PC/모바일 : https://wonclick.woorifcapital.com/\n"
            "우리금융 원톡 : https://wontalk-guest.woorifcapital.com/my-talk"
            "?ticketId=e9c5982a-0dfa-4484-8652-bf31a4138eb2",
        call="1544-8600", accident="1644-5222", takeover="02-2017-5560"),

    _company(
        "하나캐피탈", "하나",
        succ={"pay": "1회", "left": "3개월", "resale": "불가", "fee": "330,000원"},
        econtract="별도 정보 없이 전자약정 진행",
        corpdoc="본인서명사실확인서 / 연대보증계약서",
        web="PC : https://www.hanacapital.co.kr/\n모바일 : 하나캐피탈 어플설치",
        call="1800-1110", accident="1688-2040", takeover="02-2037-1390"),

    _company(
        "BNK캐피탈", "비엔케이 부산",
        succ={"pay": "1회", "left": "2개월", "resale": "불가", "fee": "330,000원",
              "note": "정산일 : 승계완료일 기준 / 이전서류 바로 발송가능 "
                      "(기간유지 없음)"},
        econtract="1. 등본\n2. 결제일자(1,5,10,15,20) 택 1\n"
                  "3. 자동이체 계좌번호\n4. 인도주소\n5. 썬팅농도\n6. 이메일주소",
        corpdoc="전자약정신청서 / 연대보증인 인감증명서",
        driver="만 69세까지 계약가능",
        web="PC/모바일 : https://web.bnkcapital.co.kr/view/prtn/logn/PrtnLogn010M01",
        call="1577-2280", accident="1644-2254", takeover="1599-9111"),

    _company(
        "KB캐피탈", "케이비 국민",
        succ={"pay": "1회", "left": "2개월", "resale": "불가",
              "fee": "220,000원 ~ 550,000원"},
        econtract="이메일 / 자택주소 / 인도지 / 계좌 / 결제일자 (1,3,5,10,15,20)",
        corpdoc="연대보증인 인감 날인 및 증명서",
        driver="만 70세까지 운전가능",
        web="PC : https://kbeasy.kbcapital.co.kr/ss/mm/MM010100.kbc?rspnCd=A#noback\n"
            "모바일 : https://kbeasy.kbcapital.co.kr/ss/co/app.kbc\n"
            "초기ID : 본인 휴대폰번호 / PW : 생년월일 앞 6자리",
        call="1544-1200", accident="1544-9770", takeover="1522-1112"),

    _company(
        "오릭스캐피탈", "오릭스 ORIX",
        succ={"pay": "3회", "left": "1개월", "resale": "가능",
              "fee": "최소 500,000원"},
        econtract="이메일 / 인도받을 주소 / 자동이체 계좌번호 / 실거주지 주소 / "
                  "임직원특약 가입여부",
        corpdoc="법인 지류약정",
        driver="만 21~70세",
        web="PC/모바일 : https://nf.orix.co.kr/",
        call="02-2050-6700", accident="1670-5330", takeover="02-2050-6700"),

    _company(
        "신한카드", "신한",
        succ={"pay": "3회", "left": "1개월", "resale": "불가",
              "fee": "최소 300,000원",
              "note": "정산일 : 승계완료일 기준 / 승계 후 최소 1회 납부 후 "
                      "완납가능 / 승계 후 완납"},
        econtract="이메일 / 주소 / 계좌 / 결제일(1,5,17,23일)",
        corpdoc="법인 지류약정",
        driver="만 74세까지 계약가능",
        web="PC/모바일 : https://mycar.shinhancard.com/adp/ADPFM860N/ADPFM860R20.shc",
        call="1544-7100", accident="1544-7751", takeover="1544-7100"),

    _company(
        "우리카드", "우카",
        succ={"pay": "1회",
              "left": "4개월  (+1~3개월일 시 완납승계 가능 · 연락처표에는 "
                      "1~3개월 사이로 적혀 있음)",
              "resale": "가능", "fee": "200,000원 ~ 1,000,000원"},
        corpdoc="법인 지류약정",
        driver="렌트 진행 X",
        web="견적기는 엑셀로 진행\n전자약정 및 조회 : "
            "https://m.wooricard.com/dcmw/yh1/mmb/mmb01/M1MMB201S00_AG.do",
        call="1544-9800", accident="1644-1199", takeover="1544-9800"),

    _company(
        "농협캐피탈", "NH 엔에이치 농협",
        succ={"pay": "1회", "left": "2개월", "resale": "불가",
              "fee": "300,000원 ~ 1,000,000원",
              "note": "정산일 : 고객 결제일 기준 / 이전서류 바로 발송가능 "
                      "(기간유지 없음)"},
        econtract="약정 내에서 직접입력",
        corpdoc="근보증서 / 확인서 / 법인인감증명서 / 등본 / 본인서명사실확인서 / "
                "지배자 체크리스트",
        driver="만 21~70세 미만",
        web="PC/모바일 : https://auto.nhcapital.co.kr/estimate/est/login.nh",
        call="1644-3700", accident="02-2038-3676", takeover="1644-3700"),

    _company(
        "삼성카드", "삼성",
        succ={"pay": "3회", "left": "1개월", "resale": "불가",
              "fee": "200,000원 ~ 500,000원"},
        corpdoc="법인 지류약정",
        driver="만 26~75세 정밀심사",
        web="별도 홈페이지 없음 / 엑셀견적",
        call="1688-3001", accident="1577-8778", takeover="02-2172-7219"),

    _company(
        "산은캐피탈", "KDB 산업은행",
        succ={"note": "참고 : 만기 3개월 → 2개월 전으로 넘어가면 위약금이 "
                      "많이 내려감"},
        econtract="이메일 / 계좌 / 결제일 (1,5,10,15,20 택1) / 등본",
        corpdoc="연대보증 계약서 2장 및 법인인감증명서, 개인인감증명서",
        driver="80세까지 접수",
        web="PC/모바일 : https://auto.kdbc.co.kr/ag/al/al100000V",
        call="1899-6114", takeover="1899-6114"),

    _company(
        "레드캡렌터카", "레드캡 redcap",
        succ={"pay": "3회", "left": "6개월", "resale": "불가", "fee": "330,000원"},
        call="1544-4599", accident="1544-4599", takeover="02-3660-2940"),

    _company(
        "오토핸즈", "오토핸즈",
        call="1800-5873", accident="1800-5873"),
]


# ---------------------------------------------------------------------------
# 보험사 사고접수
# ---------------------------------------------------------------------------
_INSURERS = [
    ("AXA손해보험", "1566-2266"), ("DB손해보험", "1588-0100"),
    ("KB손해보험", "1544-0114"), ("MG손해보험", "1588-5959"),
    ("롯데손해보험", "1588-3344"), ("메리츠화재보험", "1566-7711"),
    ("삼성화재보험", "1588-5114"), ("캐롯손해보험", "1566-0300"),
    ("하나손해보험", "1566-3000 / 1644-3000"), ("한화손해보험", "1566-8000"),
    ("현대해상보험", "1588-5656"), ("흥국화재보험", "1688-1688"),
]

INSURERS = [{
    "category": CAT_CONTACT, "finance": "", "title": "보험사 사고접수 연락처",
    "tags": "보험 보험사 사고접수 사고 손해보험 화재보험",
    "body": "■ 사고접수\n" + "\n".join(f"· {n} : {t}" for n, t in _INSURERS),
    "checklist": [],
}]


DEFAULTS = DOCS + COMPANIES + INSURERS
