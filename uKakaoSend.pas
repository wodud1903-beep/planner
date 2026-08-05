unit uKakaoSend;

{
  카카오톡 PC 채팅방 전송 엔진 (v2)

  v1 문제점
  ---------
  창 클래스명('#32770')만으로 판별해서, 카카오톡이 아닌 다른 프로그램의
  다이얼로그(UBIKeyService, _TouchEn_nxWeb 등)까지 목록에 섞여 나왔다.
  또한 메인 창 클래스명이 바뀌면 IsKakaoRunning 이 False 가 되어
  '창 목록' 버튼이 아무 반응도 하지 않았다.

  v2 개선
  -------
  1) KakaoTalk.exe 프로세스 ID 를 먼저 구한다 (ToolHelp32).
  2) 그 PID 가 소유한 최상위 창만 대상으로 삼는다 -> 타 프로그램 완전 배제.
  3) 창 클래스명에 의존하지 않고, "리치에디트 입력창을 가진 창"을
     채팅방으로 판별한다 -> 카카오톡 업데이트에 강함.
  4) 최소화된 채팅방 창은 포커스를 뺏지 않고 복원한다.

  설계 원칙 (v1과 동일)
  ---------------------
  - 물리적 키보드/마우스 입력을 발생시키지 않는다.
  - 채팅방 창이 열려 있어야 전송 가능하다. 친구 목록을 자동 탐색하거나
    채팅방을 자동 개설하지 않는다.
}

interface

uses
  Winapi.Windows, Winapi.Messages, Winapi.TlHelp32,
  System.SysUtils, System.Classes,
  Vcl.Graphics, Vcl.Clipbrd, Vcl.Imaging.pngimage, Vcl.Imaging.jpeg;

const
  // 리치에디트 관련 (Winapi.RichEdit 의존을 피하려고 직접 정의)
  EM_GETEVENTMASK_ = WM_USER + 59;   // $043B
  EM_SETEVENTMASK_ = WM_USER + 69;   // $0445
  ENM_CHANGE_      = $00000001;

type
  TSendResult = record
    Success: Boolean;
    ErrorMsg: string;
  end;

  TKakaoSender = class
  private
    class function GetKakaoPIDs: TArray<DWORD>;
    class function FindChatWindow(const ARoomName: string): HWND;
    class function PutImageToClipboard(const AFile: string): Boolean;
    class function EditLen(AEdit: HWND): Integer;
    class procedure ClearEdit(AEdit: HWND);
    class procedure EnableChangeNotify(AEdit: HWND);
    class procedure PostEnter(AWnd: HWND);
    class function TryEnter(AChat, AEdit: HWND; ADelayMs: Integer): Boolean;
    class function PutTextAndSend(AChat, AEdit: HWND; const AMsg: string;
      ADelayMs: Integer; out AMethod: string): Boolean;
    class procedure RestoreIfMinimized(H: HWND);
  public
    /// 창이 카카오톡 프로세스 소유인지
    class function IsOwnedByKakao(H: HWND; const APIDs: TArray<DWORD>): Boolean;

    /// 카카오톡 PC 프로세스가 실행 중인지
    class function IsKakaoRunning: Boolean;

    /// 창 안에서 입력용 리치에디트를 찾는다 (없으면 0)
    class function FindInputEdit(AChatWnd: HWND): HWND;

    /// 현재 열려 있는 카카오톡 채팅방 창 이름 목록
    class procedure ListChatWindows(AList: TStrings);

    /// 지정한 채팅방들 중 열려 있지 않은 방 이름을 반환
    class function CheckRoomsOpen(ARooms: TStrings): TArray<string>;

    /// 채팅방 창을 포커스를 뺏지 않고 최소화한다
    class function MinimizeRoom(const ARoomName: string): Boolean;

    /// 텍스트 전송
    class function SendText(const ARoomName, AMessage: string;
      ASendDelayMs: Integer): TSendResult;

    /// 이미지(+텍스트) 전송
    class function SendImage(const ARoomName, AMessage, AImageFile: string;
      APasteWaitMs, ASendDelayMs: Integer): TSendResult;

    /// PID 로 실행 파일명 조회
    class function ProcExeName(APID: DWORD): string;

    /// 진단 - 카카오톡 관련 프로세스/창/컨트롤 구조 전체를 문자열로 반환
    class function Diagnose(const ARoomName: string): string;
  end;

implementation

{ ---------- 공통 헬퍼 ---------- }

function GetWndClass(H: HWND): string;
var
  Buf: array[0..255] of Char;
begin
  FillChar(Buf, SizeOf(Buf), 0);
  GetClassName(H, Buf, Length(Buf));
  Result := Buf;
end;

function GetWndText(H: HWND): string;
var
  Buf: array[0..1023] of Char;
begin
  FillChar(Buf, SizeOf(Buf), 0);
  GetWindowText(H, Buf, Length(Buf));
  Result := Buf;
end;

function WndPID(H: HWND): DWORD;
begin
  Result := 0;
  GetWindowThreadProcessId(H, @Result);
end;

{ ---------- 자식 컨트롤 열거 ---------- }

type
  PEditRec = ^TEditRec;
  TEditRec = record
    LastEdit: HWND;
    EditCount: Integer;
    Dump: TStrings;   // nil 이면 덤프 안 함
  end;

function EnumChildProc(H: HWND; L: LPARAM): BOOL; stdcall;
var
  R: PEditRec;
  Cls: string;
begin
  Result := True;
  R := PEditRec(L);
  Cls := GetWndClass(H);

  if Assigned(R^.Dump) then
    R^.Dump.Add(Format('     - class=%-22s text=%s',
      [Cls, Copy(GetWndText(H), 1, 30)]));

  // RICHEDIT50W / RichEdit20W / RichEdit60W 등 계열 전부
  if Pos('RICHEDIT', UpperCase(Cls)) = 1 then
  begin
    Inc(R^.EditCount);
    R^.LastEdit := H;   // 마지막 리치에디트 = 입력창
  end;
end;

{ ---------- 최상위 창 열거 ---------- }

type
  TEnumMode = (emList, emFind, emDump);

  PTopRec = ^TTopRec;
  TTopRec = record
    PIDs: TArray<DWORD>;
    Mode: TEnumMode;
    Target: string;
    Found: HWND;
    List: TStrings;
  end;

function EnumTopProc(H: HWND; L: LPARAM): BOOL; stdcall;
var
  R: PTopRec;
  Cap, Cls: string;
  Rec: TEditRec;
begin
  Result := True;
  R := PTopRec(L);

  if not TKakaoSender.IsOwnedByKakao(H, R^.PIDs) then Exit;

  Cap := Trim(GetWndText(H));
  Cls := GetWndClass(H);

  if R^.Mode = emDump then
  begin
    R^.List.Add(Format('  HWND=%d  visible=%s  class=%s  caption=[%s]',
      [H, BoolToStr(IsWindowVisible(H), True), Cls, Cap]));
    Rec.LastEdit := 0;
    Rec.EditCount := 0;
    Rec.Dump := R^.List;
    EnumChildWindows(H, @EnumChildProc, LPARAM(@Rec));
    R^.List.Add(Format('     => 리치에디트 %d개, 입력창 후보 HWND=%d',
      [Rec.EditCount, Rec.LastEdit]));
    Exit;
  end;

  if Cap = '' then Exit;
  // 메인 창은 채팅방이 아님
  if SameText(Cap, '카카오톡') or SameText(Cap, 'KakaoTalk') then Exit;

  // 클래스명이 아니라 "입력용 리치에디트를 가졌는가"로 채팅방을 판별
  if TKakaoSender.FindInputEdit(H) = 0 then Exit;

  case R^.Mode of
    emList:
      if R^.List.IndexOf(Cap) < 0 then
        R^.List.Add(Cap);
    emFind:
      if SameText(Cap, Trim(R^.Target)) then
      begin
        R^.Found := H;
        Result := False;   // 열거 중단
      end;
  end;
end;

{ ---------- TKakaoSender ---------- }

class function TKakaoSender.GetKakaoPIDs: TArray<DWORD>;
var
  Snap: THandle;
  PE: TProcessEntry32;
  ExeName: string;
begin
  SetLength(Result, 0);
  Snap := CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0);
  if Snap = INVALID_HANDLE_VALUE then Exit;
  try
    FillChar(PE, SizeOf(PE), 0);
    PE.dwSize := SizeOf(PE);
    if Process32First(Snap, PE) then
      repeat
        ExeName := LowerCase(string(PE.szExeFile));
        // KakaoTalk.exe / KakaoTalkEdge.exe / 향후 변형까지 포괄
        if Pos('kakao', ExeName) > 0 then
        begin
          SetLength(Result, Length(Result) + 1);
          Result[High(Result)] := PE.th32ProcessID;
        end;
      until not Process32Next(Snap, PE);
  finally
    CloseHandle(Snap);
  end;
end;

class function TKakaoSender.ProcExeName(APID: DWORD): string;
var
  Snap: THandle;
  PE: TProcessEntry32;
begin
  Result := '?';
  if APID = 0 then Exit;
  Snap := CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0);
  if Snap = INVALID_HANDLE_VALUE then Exit;
  try
    FillChar(PE, SizeOf(PE), 0);
    PE.dwSize := SizeOf(PE);
    if Process32First(Snap, PE) then
      repeat
        if PE.th32ProcessID = APID then
          Exit(string(PE.szExeFile));
      until not Process32Next(Snap, PE);
  finally
    CloseHandle(Snap);
  end;
end;

class function TKakaoSender.IsOwnedByKakao(H: HWND; const APIDs: TArray<DWORD>): Boolean;
var
  P, K: DWORD;
begin
  Result := False;
  P := WndPID(H);
  if P = 0 then Exit;
  for K in APIDs do
    if K = P then
      Exit(True);
end;

class function TKakaoSender.IsKakaoRunning: Boolean;
begin
  Result := Length(GetKakaoPIDs) > 0;
end;

class function TKakaoSender.FindInputEdit(AChatWnd: HWND): HWND;
var
  Rec: TEditRec;
begin
  Rec.LastEdit := 0;
  Rec.EditCount := 0;
  Rec.Dump := nil;
  EnumChildWindows(AChatWnd, @EnumChildProc, LPARAM(@Rec));
  // 리치에디트가 1개 이상이면 마지막 것을 입력창 후보로 본다.
  // (버전에 따라 대화 영역이 커스텀 렌더링이라 리치에디트가 1개뿐일 수 있음)
  Result := Rec.LastEdit;
end;

class procedure TKakaoSender.ListChatWindows(AList: TStrings);
var
  R: TTopRec;
begin
  AList.BeginUpdate;
  try
    AList.Clear;
    R.PIDs := GetKakaoPIDs;
    if Length(R.PIDs) = 0 then Exit;
    R.Mode := emList;
    R.Target := '';
    R.Found := 0;
    R.List := AList;
    EnumWindows(@EnumTopProc, LPARAM(@R));
  finally
    AList.EndUpdate;
  end;
end;

class function TKakaoSender.CheckRoomsOpen(ARooms: TStrings): TArray<string>;
var
  Open: TStringList;
  I: Integer;
begin
  SetLength(Result, 0);
  Open := TStringList.Create;
  try
    ListChatWindows(Open);
    for I := 0 to ARooms.Count - 1 do
      if (Trim(ARooms[I]) <> '') and (Open.IndexOf(Trim(ARooms[I])) < 0) then
      begin
        SetLength(Result, Length(Result) + 1);
        Result[High(Result)] := ARooms[I];
      end;
  finally
    Open.Free;
  end;
end;

class function TKakaoSender.FindChatWindow(const ARoomName: string): HWND;
var
  R: TTopRec;
begin
  Result := 0;
  R.PIDs := GetKakaoPIDs;
  if Length(R.PIDs) = 0 then Exit;
  R.Mode := emFind;
  R.Target := ARoomName;
  R.Found := 0;
  R.List := nil;
  EnumWindows(@EnumTopProc, LPARAM(@R));
  Result := R.Found;
end;

class procedure TKakaoSender.RestoreIfMinimized(H: HWND);
begin
  // 포커스를 뺏지 않고 복원한다
  if IsIconic(H) then
  begin
    ShowWindow(H, SW_SHOWNOACTIVATE);
    Sleep(300);
  end;
end;

class function TKakaoSender.MinimizeRoom(const ARoomName: string): Boolean;
var
  H: HWND;
begin
  H := FindChatWindow(ARoomName);
  Result := H <> 0;
  if Result and (not IsIconic(H)) then
    ShowWindow(H, SW_SHOWMINNOACTIVE);   // 포커스를 뺏지 않고 최소화
end;

class function TKakaoSender.EditLen(AEdit: HWND): Integer;
begin
  Result := SendMessage(AEdit, WM_GETTEXTLENGTH, 0, 0);
end;

class procedure TKakaoSender.PostEnter(AWnd: HWND);
const
  LP_DOWN = $001C0001;   // repeat=1, scancode=$1C(Enter)
  LP_UP   = $C01C0001;
begin
  PostMessage(AWnd, WM_KEYDOWN, VK_RETURN, LP_DOWN);
  PostMessage(AWnd, WM_CHAR,    VK_RETURN, LP_DOWN);
  PostMessage(AWnd, WM_KEYUP,   VK_RETURN, LP_UP);
end;

{
  엔터(전송) 처리.
  단순 WM_KEYDOWN 만으로는 카카오톡이 '전송'으로 인식하지 않는 경우가 있어
  3단계로 시도하고, 매 단계마다 입력창이 비었는지로 성공 여부를 검증한다.
}
class function TKakaoSender.TryEnter(AChat, AEdit: HWND; ADelayMs: Integer): Boolean;
var
  L: Integer;
  MyTid, TgtTid: DWORD;
begin
  // --- 1단계: 캐럿을 끝으로 옮기고 컨트롤에 직접 키 메시지 ---
  L := EditLen(AEdit);
  SendMessage(AEdit, EM_SETSEL, WPARAM(L), LPARAM(L));
  PostEnter(AEdit);
  Sleep(ADelayMs);
  if EditLen(AEdit) = 0 then Exit(True);

  // --- 2단계: 입력 큐를 붙여 '논리적 포커스'를 준 뒤 재시도 ---
  // (물리적 키보드 입력이 아니라, 스레드 입력 상태만 연결하는 방식)
  TgtTid := GetWindowThreadProcessId(AChat, nil);
  MyTid := GetCurrentThreadId;
  if (TgtTid <> 0) and AttachThreadInput(MyTid, TgtTid, True) then
  begin
    try
      Winapi.Windows.SetFocus(AEdit);
      Sleep(80);
      PostEnter(AEdit);
      Sleep(ADelayMs);
    finally
      AttachThreadInput(MyTid, TgtTid, False);
    end;
    if EditLen(AEdit) = 0 then Exit(True);
  end;

  // --- 3단계: 부모(채팅방) 창으로 키 메시지 전달 ---
  PostEnter(AChat);
  Sleep(ADelayMs);
  Result := EditLen(AEdit) = 0;
end;

class procedure TKakaoSender.ClearEdit(AEdit: HWND);
begin
  SendMessage(AEdit, EM_SETSEL, 0, LPARAM(-1));
  SendMessage(AEdit, EM_REPLACESEL, WPARAM(1), LPARAM(PChar('')));
end;

class procedure TKakaoSender.EnableChangeNotify(AEdit: HWND);
var
  M: LRESULT;
begin
  // 카카오톡이 EN_CHANGE 를 못 받으면 전송 버튼이 활성화되지 않는다
  M := SendMessage(AEdit, EM_GETEVENTMASK_, 0, 0);
  SendMessage(AEdit, EM_SETEVENTMASK_, 0, M or ENM_CHANGE_);
end;

{
  텍스트를 입력창에 넣고 전송한다.

  WM_SETTEXT 는 리치에디트에서 EN_CHANGE 통지를 발생시키지 않는다.
  그래서 글자는 보이는데 카카오톡 내부적으로는 "입력 없음" 상태로 남아
  전송 버튼이 활성화되지 않는다. 아래 3가지 방식을 순서대로 시도한다.

    A. EM_REPLACESEL   - 사용자가 타이핑한 것과 동일하게 처리되어 통지가 발생
    B. 클립보드 + WM_PASTE - 컨트롤의 붙여넣기 경로를 그대로 탐
    C. WM_CHAR 한 글자씩 - 가장 키보드 입력에 가까움 (줄바꿈은 공백으로 대체)
}
class function TKakaoSender.PutTextAndSend(AChat, AEdit: HWND; const AMsg: string;
  ADelayMs: Integer; out AMethod: string): Boolean;
var
  Msg: string;
  I: Integer;
  Ch: Char;
  Saved: string;
begin
  Msg := StringReplace(AMsg, #13#10, #13, [rfReplaceAll]);
  Msg := StringReplace(Msg, #10, #13, [rfReplaceAll]);

  EnableChangeNotify(AEdit);

  // ---------- 방식 A : EM_REPLACESEL ----------
  AMethod := 'EM_REPLACESEL';
  ClearEdit(AEdit);
  SendMessage(AEdit, EM_SETSEL, 0, 0);
  SendMessage(AEdit, EM_REPLACESEL, WPARAM(1), LPARAM(PChar(Msg)));
  Sleep(ADelayMs);
  if TryEnter(AChat, AEdit, ADelayMs) then Exit(True);

  // ---------- 방식 B : 클립보드 붙여넣기 ----------
  AMethod := 'WM_PASTE';
  ClearEdit(AEdit);
  Saved := '';
  try
    if Clipboard.HasFormat(CF_UNICODETEXT) then
      Saved := Clipboard.AsText;
  except
    Saved := '';
  end;
  try
    Clipboard.AsText := Msg;
  except
    // 클립보드 점유 실패 시 다음 방식으로
  end;
  Sleep(120);
  SendMessage(AEdit, WM_PASTE, 0, 0);
  Sleep(ADelayMs);
  if TryEnter(AChat, AEdit, ADelayMs) then
  begin
    if Saved <> '' then
      try Clipboard.AsText := Saved; except end;
    Exit(True);
  end;
  if Saved <> '' then
    try Clipboard.AsText := Saved; except end;

  // ---------- 방식 C : WM_CHAR 한 글자씩 ----------
  AMethod := 'WM_CHAR';
  ClearEdit(AEdit);
  for I := 1 to Length(Msg) do
  begin
    Ch := Msg[I];
    if Ch = #13 then
      Ch := ' ';   // 줄바꿈은 Shift+Enter 가 필요해 이 방식에서는 공백 처리
    PostMessage(AEdit, WM_CHAR, WPARAM(Ord(Ch)), 1);
  end;
  Sleep(ADelayMs);
  Result := TryEnter(AChat, AEdit, ADelayMs);
end;

class function TKakaoSender.SendText(const ARoomName, AMessage: string;
  ASendDelayMs: Integer): TSendResult;
var
  hChat, hEdit: HWND;
  Method: string;
  WasMin: Boolean;
begin
  Result.Success := False;
  Result.ErrorMsg := '';

  if Trim(AMessage) = '' then
  begin
    Result.ErrorMsg := '보낼 메시지가 비어 있습니다';
    Exit;
  end;

  if not IsKakaoRunning then
  begin
    Result.ErrorMsg := '카카오톡 PC(KakaoTalk.exe)가 실행되어 있지 않습니다';
    Exit;
  end;

  hChat := FindChatWindow(ARoomName);
  if hChat = 0 then
  begin
    Result.ErrorMsg := Format('채팅방 창을 찾을 수 없습니다 [%s] - 채팅방을 미리 열어두세요',
      [ARoomName]);
    Exit;
  end;

  WasMin := IsIconic(hChat);
  RestoreIfMinimized(hChat);

  hEdit := FindInputEdit(hChat);
  if hEdit = 0 then
  begin
    Result.ErrorMsg := '입력창(RichEdit)을 찾지 못했습니다 - [구조 진단]으로 확인 필요';
    if WasMin then ShowWindow(hChat, SW_SHOWMINNOACTIVE);
    Exit;
  end;

  SendMessage(hEdit, WM_SETTEXT, 0, LPARAM(PChar('')));

  if PutTextAndSend(hChat, hEdit, AMessage, ASendDelayMs, Method) then
  begin
    Result.Success := True;
    Result.ErrorMsg := Method;   // 성공한 입력 방식 (로그 참고용)
  end
  else
  begin
    Result.Success := False;
    Result.ErrorMsg := '3가지 입력 방식(EM_REPLACESEL / 붙여넣기 / WM_CHAR) 모두 ' +
      '전송되지 않았습니다 - 전송 간격(ms)을 2000 이상으로 올려보세요';
  end;

  // 원래 최소화 상태였다면 작업 방해가 없도록 되돌린다
  if WasMin then
    ShowWindow(hChat, SW_SHOWMINNOACTIVE);
end;

class function TKakaoSender.PutImageToClipboard(const AFile: string): Boolean;
var
  Pic: TPicture;
  Bmp: TBitmap;
begin
  Result := False;
  if not FileExists(AFile) then Exit;

  Pic := TPicture.Create;
  Bmp := TBitmap.Create;
  try
    try
      Pic.LoadFromFile(AFile);
      Bmp.PixelFormat := pf24bit;
      Bmp.SetSize(Pic.Width, Pic.Height);
      Bmp.Canvas.Brush.Color := clWhite;
      Bmp.Canvas.FillRect(Rect(0, 0, Bmp.Width, Bmp.Height));
      Bmp.Canvas.Draw(0, 0, Pic.Graphic);
      Clipboard.Assign(Bmp);
      Result := True;
    except
      Result := False;
    end;
  finally
    Bmp.Free;
    Pic.Free;
  end;
end;

class function TKakaoSender.SendImage(const ARoomName, AMessage, AImageFile: string;
  APasteWaitMs, ASendDelayMs: Integer): TSendResult;
var
  hChat, hEdit: HWND;
  Method: string;
  WasMin: Boolean;
begin
  Result.Success := False;
  Result.ErrorMsg := '';

  if not FileExists(AImageFile) then
  begin
    Result.ErrorMsg := Format('이미지 파일이 없습니다 [%s]', [AImageFile]);
    Exit;
  end;

  if not IsKakaoRunning then
  begin
    Result.ErrorMsg := '카카오톡 PC(KakaoTalk.exe)가 실행되어 있지 않습니다';
    Exit;
  end;

  hChat := FindChatWindow(ARoomName);
  if hChat = 0 then
  begin
    Result.ErrorMsg := Format('채팅방 창을 찾을 수 없습니다 [%s] - 채팅방을 미리 열어두세요',
      [ARoomName]);
    Exit;
  end;

  WasMin := IsIconic(hChat);
  RestoreIfMinimized(hChat);

  hEdit := FindInputEdit(hChat);
  if hEdit = 0 then
  begin
    Result.ErrorMsg := '입력창(RichEdit)을 찾지 못했습니다';
    if WasMin then ShowWindow(hChat, SW_SHOWMINNOACTIVE);
    Exit;
  end;

  if not PutImageToClipboard(AImageFile) then
  begin
    Result.ErrorMsg := '이미지를 클립보드에 올리지 못했습니다 (포맷 확인)';
    if WasMin then ShowWindow(hChat, SW_SHOWMINNOACTIVE);
    Exit;
  end;

  SendMessage(hEdit, WM_PASTE, 0, 0);
  Sleep(APasteWaitMs);
  TryEnter(hChat, hEdit, ASendDelayMs);   // 이미지 전송
  Sleep(ASendDelayMs);

  if Trim(AMessage) <> '' then
  begin
    if not PutTextAndSend(hChat, hEdit, AMessage, ASendDelayMs, Method) then
    begin
      Result.ErrorMsg := '이미지는 보냈으나 캡션 텍스트 전송이 처리되지 않았습니다';
      if WasMin then ShowWindow(hChat, SW_SHOWMINNOACTIVE);
      Exit;
    end;
  end;

  Result.Success := True;
  if WasMin then
    ShowWindow(hChat, SW_SHOWMINNOACTIVE);
end;

{ 전체 최상위 창 덤프용 (카카오 여부 무관) }

function EnumAllTopProc(H: HWND; L: LPARAM): BOOL; stdcall;
var
  SL: TStrings;
  Cap, Exe: string;
  PID: DWORD;
begin
  Result := True;
  SL := TStrings(L);
  if not IsWindowVisible(H) then Exit;
  Cap := Trim(GetWndText(H));
  if Cap = '' then Exit;
  PID := WndPID(H);
  Exe := TKakaoSender.ProcExeName(PID);
  SL.Add(Format('  PID=%-6d exe=%-24s class=%-24s caption=[%s]',
    [PID, Exe, GetWndClass(H), Cap]));
end;

class function TKakaoSender.Diagnose(const ARoomName: string): string;
var
  SL: TStringList;
  R: TTopRec;
  PIDs: TArray<DWORD>;
  P: DWORD;
begin
  SL := TStringList.Create;
  try
    SL.Add('===== 카카오톡 구조 진단 =====');

    PIDs := GetKakaoPIDs;

    if Length(PIDs) = 0 then
    begin
      SL.Add('[1] 이름에 "kakao" 가 들어간 프로세스를 찾지 못했습니다.');
      SL.Add('');
      SL.Add('[2] 현재 화면에 보이는 모든 창 (여기서 카카오톡 줄을 찾아 알려주세요)');
      EnumWindows(@EnumAllTopProc, LPARAM(SL));
      SL.Add('==============================');
      Exit(SL.Text);
    end;

    SL.Add('[1] 카카오 관련 프로세스');
    for P in PIDs do
      SL.Add(Format('    PID=%d  exe=%s', [P, ProcExeName(P)]));

    SL.Add('');
    SL.Add('[2] 해당 프로세스가 소유한 최상위 창 + 자식 컨트롤');

    R.PIDs := PIDs;
    R.Mode := emDump;
    R.Target := '';
    R.Found := 0;
    R.List := SL;
    EnumWindows(@EnumTopProc, LPARAM(@R));

    SL.Add('');
    SL.Add('[3] 화면에 보이는 모든 창 (카카오 창이 위 목록에 없을 때 대조용)');
    EnumWindows(@EnumAllTopProc, LPARAM(SL));

    SL.Add('');
    if Trim(ARoomName) <> '' then
    begin
      if FindChatWindow(ARoomName) <> 0 then
        SL.Add(Format('[4] [%s] -> 채팅방 창 찾음 (OK)', [ARoomName]))
      else
        SL.Add(Format('[4] [%s] -> 채팅방 창 못 찾음', [ARoomName]));
    end;
    SL.Add('==============================');
    Result := SL.Text;
  finally
    SL.Free;
  end;
end;

end.
