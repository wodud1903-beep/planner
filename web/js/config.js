// 웹앱 설정.
//
// 클라이언트 ID 는 브라우저에 어차피 드러나는 값이라 공개 저장소에 있어도 된다.
// 지켜 주는 것은 구글 콘솔에 등록한 **원본(origin) 제한**이다 — 이 주소에서 온
// 요청만 받아 준다. 그래서 시크릿은 쓰지 않는다(웹 시크릿은 진짜 비밀이라
// 브라우저에 둘 수 없고, 토큰 방식은 필요도 없다).
export const CLIENT_ID =
  "593737105209-o24o5moa3k2lo3hqivkgl6stpogpqgnf.apps.googleusercontent.com";

// 회사 공용 시트 — 자료검색(업무자료)·수당율이 들어 있다. PC 앱과 같은 값.
export const RATES_SHEET_ID = "1PSjqA7wvIBHusjYHFfD9cLKP-EbtdFrCkNqlZHz2jm0";
export const KB_TAB = "업무자료";

// 고객관리 시트 — **기본값을 두지 않는다.**
//
// ⚠️ 예전에는 실제 시트 주소가 박혀 있었다. 그래서 다른 직원이 자기 계정으로
//    로그인해도 그 주소가 그대로 들어가 있어 남의 고객 목록이 열렸다.
//    쓰는 사람이 [시트 설정] 에서 직접 넣는다.
export const DEF_SHEET_ID = "";
export const DEF_SHEET_NAME = "미출고차량";

export const SCOPES = [
  "openid",
  "email",
  // ⚠️ 읽기 전용이 아니다. 폰에서 고객 정보를 고칠 수 있게 되면서 쓰기가 필요해졌다.
  //    이 줄을 바꾸면 기존 토큰에는 그 권한이 없어 403 이 오는데, 그건
  //    NeedScope 로 잡아 '다시 로그인' 이라고 안내한다(sheets.js).
  "https://www.googleapis.com/auth/spreadsheets",
  "https://www.googleapis.com/auth/drive.readonly",
  // 일정은 보기만 한다 — 폰에서 일정을 고칠 일은 PC 에서 하면 되고,
  // 쓰기 권한을 들고 다니면 폰을 잃었을 때 잃을 것이 늘어난다.
  "https://www.googleapis.com/auth/calendar.readonly",
  // 할일은 **체크**까지 한다. 밖에서 '했다' 를 누르는 게 이 화면의 쓸모다.
  "https://www.googleapis.com/auth/tasks",
  // 앱 전용 숨김 폴더 — 시트 주소·서류 폴더를 **계정에 붙여** 보관한다.
  // 브라우저에 두면 기기마다 다시 입력해야 하고, 기기를 바꾸면 사라진다.
  // PC 앱이 이미 여기에 설정을 올리고 있어서 그것도 그대로 읽어 온다.
  "https://www.googleapis.com/auth/drive.appdata",
].join(" ");

export const CALENDAR_API = "https://www.googleapis.com/calendar/v3";
export const TASKS_API = "https://tasks.googleapis.com/tasks/v1";

export const SHEETS_API = "https://sheets.googleapis.com/v4/spreadsheets";
