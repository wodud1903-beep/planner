/**
 * 야간 정리 — 고객관리 스프레드시트에 붙이는 Apps Script.
 *
 * PC 가 꺼져 있어도 매일 새벽에 혼자 돌면서 두 가지를 정리해 둔다.
 *
 *   1) [만기예정]  계약조건의 '60개월' 표기로 만기일을 계산해,
 *                  앞으로 N개월 안에 만기가 오는 고객을 급한 순으로 모은다.
 *   2) [정체건]    진행현황이 며칠째 그대로인 건을 오래된 순으로 모은다.
 *                  시트에는 '언제 바뀌었는지' 가 없으므로, 이 스크립트가
 *                  스스로 [_정리기록] 탭에 어제 값을 적어 두고 비교한다.
 *
 * ── 넣는 법 ────────────────────────────────────────────────────────────
 *  1. 고객관리 스프레드시트를 연다
 *  2. 확장 프로그램 → Apps Script
 *  3. 이 파일 내용을 통째로 붙여넣고 저장 (Ctrl+S)
 *  4. 함수 목록에서 `야간정리` 를 고르고 [실행] → 권한 허용 한 번
 *  5. 왼쪽 ⏰(트리거) → [트리거 추가]
 *       실행할 함수: 야간정리
 *       이벤트 소스: 시간 기반
 *       트리거 유형: 일 단위 타이머
 *       시간 선택  : 오전 4시~5시
 *
 * ── 안전장치 ───────────────────────────────────────────────────────────
 *  · 원본 데이터를 **읽기만** 한다. 고객 시트에는 한 글자도 쓰지 않는다.
 *  · 만드는 탭 3개(만기예정 / 정체건 / _정리기록) 밖으로 나가지 않는다.
 *  · 탭 이름이 겹치면 새로 만들지 않고 그 탭을 다시 채운다.
 */

// ── 설정 ────────────────────────────────────────────────────────────────
var 설정 = {
  원본탭: '고객관리',     // 읽어올 탭 이름 (앱 설정의 '시트(탭) 이름' 과 같게)
  만기탭: '만기예정',
  정체탭: '정체건',
  기록탭: '_정리기록',    // 스크립트가 쓰는 숨김 탭 — 손대지 마세요
  만기개월: 6,            // 앞으로 몇 개월 안의 만기를 모을지
  정체일수: 14,           // 진행현황이 며칠째 그대로면 정체로 볼지
  끝난상태: ['출고', '완료', '취소'],   // 이 말로 시작하면 이미 끝난 건
  보류상태: ['진행보류', '보류', '홀딩'] // 이 말로 시작하면 기다리는 건(정체 아님)
};

// 열 번호 (A=1). 앱의 sheets.py 와 같은 자리다.
var 열 = {
  순번: 1, 고객명: 2, 금융사: 3, 차종: 4, 계약일: 10, 출고일: 11,
  진행현황: 12, 계약조건: 13, 고객ID: 21
};

var 머리글찾기_최대행 = 30;   // 위쪽 요약행이 몇 줄 있어서 헤더를 찾아 내려간다


// ── 진입점 ──────────────────────────────────────────────────────────────
function 야간정리() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var 원본 = ss.getSheetByName(설정.원본탭);
  if (!원본) {
    throw new Error("'" + 설정.원본탭 + "' 탭을 찾지 못했습니다. 설정.원본탭 을 확인하세요.");
  }

  var 고객들 = 고객읽기_(원본);
  if (!고객들.length) return;   // 빈 시트 — 아무것도 지우지 않고 그냥 끝낸다

  var 오늘 = 자정_(new Date());
  var 기록 = 기록읽기_(ss);

  만기탭쓰기_(ss, 만기예정_(고객들, 오늘));
  정체탭쓰기_(ss, 정체건_(고객들, 오늘, 기록));
  기록쓰기_(ss, 기록갱신_(고객들, 오늘, 기록));
}


// ── 원본 읽기 ───────────────────────────────────────────────────────────
function 고객읽기_(시트) {
  var 값 = 시트.getDataRange().getDisplayValues();
  var 머리 = 머리글행_(값);
  if (머리 < 0) {
    throw new Error("'순번 / 고객명' 머리글 행을 찾지 못했습니다.");
  }
  var out = [];
  for (var i = 머리 + 1; i < 값.length; i++) {
    var r = 값[i];
    var 이름 = (r[열.고객명 - 1] || '').trim();
    if (!이름) continue;                 // 고객명이 없으면 빈 줄로 본다
    out.push({
      행: i + 1,
      순번: (r[열.순번 - 1] || '').trim(),
      고객명: 이름,
      금융사: (r[열.금융사 - 1] || '').trim(),
      차종: (r[열.차종 - 1] || '').trim(),
      계약일: 날짜읽기_(r[열.계약일 - 1]),
      출고일: 날짜읽기_(r[열.출고일 - 1]),
      진행현황: (r[열.진행현황 - 1] || '').trim(),
      계약조건: (r[열.계약조건 - 1] || '').trim(),
      고객ID: (r[열.고객ID - 1] || '').trim()
    });
  }
  return out;
}

function 머리글행_(값) {
  var 끝 = Math.min(머리글찾기_최대행, 값.length);
  for (var i = 0; i < 끝; i++) {
    var a = (값[i][0] || '').trim();
    var b = (값[i][1] || '').trim();
    if (a.indexOf('순번') === 0 && b.indexOf('고객명') >= 0) return i;
  }
  return -1;
}

/** '2026. 8. 14' / '2026-08-14' / '2026년 8월 14일' → Date. 못 읽으면 null. */
function 날짜읽기_(s) {
  var t = (s || '').toString().trim();
  if (!t) return null;
  var m = t.match(/(\d{4})\s*[.\-\/년]\s*(\d{1,2})\s*[.\-\/월]\s*(\d{1,2})/);
  if (!m) return null;
  var y = +m[1], mo = +m[2], d = +m[3];
  if (mo < 1 || mo > 12 || d < 1 || d > 31) return null;
  var dt = new Date(y, mo - 1, d);
  // 2월 30일 같은 값이 3월로 넘어가 버리는 것을 걸러 낸다
  if (dt.getFullYear() !== y || dt.getMonth() !== mo - 1 || dt.getDate() !== d) return null;
  return dt;
}

function 자정_(d) { return new Date(d.getFullYear(), d.getMonth(), d.getDate()); }

function 일수차_(a, b) {
  return Math.round((자정_(a) - 자정_(b)) / 86400000);
}

function 개월더하기_(d, n) {
  var y = d.getFullYear(), m = d.getMonth() + n, day = d.getDate();
  var 말일 = new Date(y, m + 1, 0).getDate();    // 그 달의 마지막 날
  return new Date(y, m, Math.min(day, 말일));
}

function 날짜글_(d) {
  return Utilities.formatDate(d, Session.getScriptTimeZone(), 'yyyy-MM-dd');
}

function 시작하나_(s, 목록) {
  for (var i = 0; i < 목록.length; i++) {
    if (s.indexOf(목록[i]) === 0) return true;
  }
  return false;
}


// ── 1) 만기예정 ─────────────────────────────────────────────────────────
/** 계약조건에서 계약기간(개월). '60개월 / 2만km' → 60. 없으면 null. */
function 계약개월_(조건) {
  var m = (조건 || '').match(/(\d{1,3})\s*개\s*월/);
  if (!m) return null;
  var n = +m[1];
  return (n >= 1 && n <= 120) ? n : null;
}

/** 만기일 = (출고일 또는 계약일) + 계약기간. 앱의 expiry_date 와 같은 규칙. */
function 만기일_(고객) {
  var n = 계약개월_(고객.계약조건);
  if (!n) return null;
  var 기준 = 고객.출고일 || 고객.계약일;
  if (!기준) return null;
  return 개월더하기_(기준, n);
}

function 만기예정_(고객들, 오늘) {
  var 한계 = 개월더하기_(오늘, 설정.만기개월);
  var out = [];
  for (var i = 0; i < 고객들.length; i++) {
    var c = 고객들[i];
    if (c.진행현황.indexOf('취소') === 0) continue;   // 취소된 계약은 만기도 없다
    var d = 만기일_(c);
    if (!d) continue;
    if (d < 오늘 || d > 한계) continue;
    out.push({
      dday: 일수차_(d, 오늘),
      줄: ['D-' + 일수차_(d, 오늘), 날짜글_(d), c.고객명, c.금융사, c.차종,
           c.계약조건, c.진행현황, c.순번]
    });
  }
  out.sort(function (a, b) { return a.dday - b.dday; });   // 급한 순
  return out.map(function (x) { return x.줄; });
}

function 만기탭쓰기_(ss, 줄들) {
  var 머리 = ['남은일수', '만기일', '고객명', '금융사', '차종', '계약조건', '진행현황', '순번'];
  탭채우기_(ss, 설정.만기탭, 머리, 줄들,
    설정.만기개월 + '개월 이내 만기 예정 · ' + 날짜글_(new Date()) + ' 자동 정리');
}


// ── 2) 정체건 ───────────────────────────────────────────────────────────
function 정체건_(고객들, 오늘, 기록) {
  var out = [];
  for (var i = 0; i < 고객들.length; i++) {
    var c = 고객들[i];
    var st = c.진행현황;
    if (시작하나_(st, 설정.끝난상태)) continue;   // 이미 끝난 건
    if (시작하나_(st, 설정.보류상태)) continue;   // 기다리는 건 — 재촉할 대상 아님
    if (c.출고일) continue;                       // 출고일이 잡혔으면 진행 중이 아니다
    if (!c.계약일 || c.계약일 > 오늘) continue;   // 아직 계약 전

    var 키 = 키_(c);
    var 이전 = 기록[키];
    // 기록이 있고 상태가 그대로면 '마지막으로 바뀐 날' 부터 센다.
    // 기록이 없으면(처음 도는 날) 계약일부터 센다 — 없는 날짜를 지어내지 않는다.
    var 기준 = (이전 && 이전.상태 === st && 이전.날짜) ? 이전.날짜 : c.계약일;
    var 며칠 = 일수차_(오늘, 기준);
    if (며칠 < 설정.정체일수) continue;
    out.push({
      일수: 며칠,
      줄: [며칠 + '일째', st || '(비어 있음)', c.고객명, c.금융사, c.차종,
           날짜글_(c.계약일), 날짜글_(기준), c.순번]
    });
  }
  out.sort(function (a, b) { return b.일수 - a.일수; });   // 오래 묵은 순
  return out.map(function (x) { return x.줄; });
}

function 정체탭쓰기_(ss, 줄들) {
  var 머리 = ['멈춘일수', '진행현황', '고객명', '금융사', '차종',
              '계약일', '이 상태가 된 날', '순번'];
  탭채우기_(ss, 설정.정체탭, 머리, 줄들,
    '진행현황이 ' + 설정.정체일수 + '일 이상 그대로인 건 · '
    + 날짜글_(new Date()) + ' 자동 정리');
}


// ── 기록 (스크립트의 기억) ──────────────────────────────────────────────
/** 고객ID 가 있으면 그것을, 없으면 이름+계약일을 열쇠로 쓴다. */
function 키_(c) {
  if (c.고객ID) return 'id:' + c.고객ID;
  return 'nm:' + c.고객명 + '|' + (c.계약일 ? 날짜글_(c.계약일) : '');
}

function 기록읽기_(ss) {
  var sh = ss.getSheetByName(설정.기록탭);
  var out = {};
  if (!sh) return out;
  var v = sh.getDataRange().getDisplayValues();
  for (var i = 1; i < v.length; i++) {              // 0번은 머리글
    var 키 = (v[i][0] || '').trim();
    if (!키) continue;
    out[키] = { 상태: (v[i][1] || '').trim(), 날짜: 날짜읽기_(v[i][2]) };
  }
  return out;
}

function 기록갱신_(고객들, 오늘, 기록) {
  var out = [];
  for (var i = 0; i < 고객들.length; i++) {
    var c = 고객들[i];
    var 키 = 키_(c);
    var 이전 = 기록[키];
    // 상태가 그대로면 '바뀐 날' 을 그대로 두고, 달라졌으면 오늘로 새로 적는다.
    var 날 = (이전 && 이전.상태 === c.진행현황 && 이전.날짜) ? 이전.날짜 : 오늘;
    out.push([키, c.진행현황, 날짜글_(날), c.고객명]);
  }
  return out;
}

function 기록쓰기_(ss, 줄들) {
  var sh = 탭준비_(ss, 설정.기록탭);
  sh.clear();
  sh.getRange(1, 1, 1, 4)
    .setValues([['열쇠', '진행현황', '이 상태가 된 날', '고객명(참고용)']])
    .setFontWeight('bold');
  if (줄들.length) {
    sh.getRange(2, 1, 줄들.length, 4).setValues(줄들);
  }
  sh.hideSheet();     // 사람이 볼 탭이 아니다
}


// ── 탭 만들기 / 채우기 ──────────────────────────────────────────────────
function 탭준비_(ss, 이름) {
  var sh = ss.getSheetByName(이름);
  if (!sh) sh = ss.insertSheet(이름);
  return sh;
}

function 탭채우기_(ss, 이름, 머리, 줄들, 안내) {
  var sh = 탭준비_(ss, 이름);
  sh.clear();
  sh.getRange(1, 1).setValue(안내).setFontColor('#666666');
  sh.getRange(2, 1, 1, 머리.length).setValues([머리])
    .setFontWeight('bold').setBackground('#EFEFEF');
  if (줄들.length) {
    sh.getRange(3, 1, 줄들.length, 머리.length).setValues(줄들);
  } else {
    sh.getRange(3, 1).setValue('(해당 없음)').setFontColor('#999999');
  }
  sh.setFrozenRows(2);
  sh.autoResizeColumns(1, 머리.length);
}


// ── 손으로 확인할 때 ────────────────────────────────────────────────────
/** 메뉴에서 바로 돌려 볼 수 있게. 트리거와 같은 일을 한다. */
function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu('야간정리')
    .addItem('지금 정리하기', '야간정리')
    .addToUi();
}
