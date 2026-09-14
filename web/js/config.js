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

// 고객관리 시트 기본값 — 설정에서 바꿀 수 있게 할 예정
export const DEF_SHEET_ID = "1L6UwkuywIEAffPvQX9GWwsP8Ix_6fP8uakNFfV1iAm8";
export const DEF_SHEET_NAME = "미출고차량";

export const SCOPES = [
  "openid",
  "email",
  "https://www.googleapis.com/auth/spreadsheets.readonly",
  "https://www.googleapis.com/auth/drive.readonly",
].join(" ");

export const SHEETS_API = "https://sheets.googleapis.com/v4/spreadsheets";
