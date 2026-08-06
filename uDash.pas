unit uDash;

{
  일정관리기 (메인 화면)
  - 탭1: 오늘/이번주 구글 캘린더(ICS) 일정
  - 탭2: 내 할일 (로컬, 알람+멘트)
  - 탭3: PC 알람 (요일/시간 반복, 최상단 팝업+멘트복사)
  - 우상단: 카카오톡 스케줄러 열기

  구글 캘린더는 ICS URL 구독 방식. 날짜가 지정된 구글 '할일'은
  캘린더에 표시되어 이 피드에 함께 들어온다.
}

interface

uses
  Winapi.Windows, Winapi.Messages, System.SysUtils, System.Classes,
  System.IOUtils, System.DateUtils, System.StrUtils, System.JSON,
  System.Generics.Collections, System.Generics.Defaults, System.Win.Registry,
  Vcl.Graphics, Vcl.Controls, Vcl.Forms, Vcl.Dialogs, Vcl.StdCtrls,
  Vcl.ExtCtrls, Vcl.ComCtrls, Vcl.Menus, Vcl.Clipbrd,
  uCalendar, uPlanData, uPlanEdit, uAlarm, uGoogleTasks, uGSettings, uGoogleDrive;

type
  TfrmDash = class(TForm)
    pnlTop: TPanel;
    lblApp: TLabel;
    btnScheduler: TButton;
    chkStartup: TCheckBox;
    pgc: TPageControl;
    tsMain: TTabSheet;
    pnlCalTop: TPanel;
    lblGStatus: TLabel;
    btnSettings: TButton;
    btnFetch: TButton;
    chkAutoFetch: TCheckBox;
    lblWeek: TLabel;
    lvWeek: TListView;
    pnlTodoBtn: TPanel;
    lblTodo: TLabel;
    btnTodoAdd: TButton;
    btnTodoEdit: TButton;
    btnTodoDel: TButton;
    btnTodoDone: TButton;
    btnTodoCopy: TButton;
    lvTodo: TListView;
    tsPcAlarm: TTabSheet;
    pnlAlarmBtn: TPanel;
    btnAlAdd: TButton;
    btnAlEdit: TButton;
    btnAlDel: TButton;
    btnAlTest: TButton;
    lvAlarm: TListView;
    Timer1: TTimer;
    TrayIcon1: TTrayIcon;
    PopupMenu1: TPopupMenu;
    miShow: TMenuItem;
    miScheduler: TMenuItem;
    miBrief: TMenuItem;
    miBackup: TMenuItem;
    miDrive: TMenuItem;
    miDiag: TMenuItem;
    miExit: TMenuItem;
    procedure FormCreate(Sender: TObject);
    procedure FormDestroy(Sender: TObject);
    procedure FormCloseQuery(Sender: TObject; var CanClose: Boolean);
    procedure Timer1Timer(Sender: TObject);
    procedure btnSchedulerClick(Sender: TObject);
    procedure chkStartupClick(Sender: TObject);
    procedure btnFetchClick(Sender: TObject);
    procedure btnSettingsClick(Sender: TObject);
    procedure btnTodoAddClick(Sender: TObject);
    procedure btnTodoEditClick(Sender: TObject);
    procedure btnTodoDelClick(Sender: TObject);
    procedure btnTodoDoneClick(Sender: TObject);
    procedure btnTodoCopyClick(Sender: TObject);
    procedure lvTodoDblClick(Sender: TObject);
    procedure lvWeekCustomDrawItem(Sender: TCustomListView;
      Item: TListItem; State: TCustomDrawState; var DefaultDraw: Boolean);
    procedure lvTodoCustomDrawItem(Sender: TCustomListView;
      Item: TListItem; State: TCustomDrawState; var DefaultDraw: Boolean);
    procedure btnAlAddClick(Sender: TObject);
    procedure btnAlEditClick(Sender: TObject);
    procedure btnAlDelClick(Sender: TObject);
    procedure btnAlTestClick(Sender: TObject);
    procedure lvAlarmDblClick(Sender: TObject);
    procedure TrayIcon1DblClick(Sender: TObject);
    procedure miShowClick(Sender: TObject);
    procedure miBriefClick(Sender: TObject);
    procedure miBackupClick(Sender: TObject);
    procedure miDriveClick(Sender: TObject);
    procedure miDiagClick(Sender: TObject);
    procedure miExitClick(Sender: TObject);
  private
    FDir: string;
    FTodoFile: string;
    FAlarmFile: string;
    FTaskAlarmFile: string;
    FCfgFile: string;
    FTodos: TTodoList;
    FAlarms: TPcAlarmList;
    FTaskAlarms: TTaskAlarmList;
    FCalCache: TCalEventList;   // 마지막으로 받은 캘린더 이벤트
    FGAuth: TGoogleAuth;
    FGTasks: TGoogleTaskList;   // 마지막으로 받은 구글 할일
    FWeekDates: TList<TDateTime>;   // 주간뷰 행별 날짜(강조 판단용)
    FTodoDates: TList<TDateTime>;   // 할일 목록 행별 날짜(강조 판단용)
    FDuplicate: Boolean;            // 두 번째로 생성된 중복 인스턴스인지
    FBootTicks: Integer;            // 부팅 직후 창을 앞으로 끌어올리기 위한 카운터
    FSet: TAppSettings;             // 전역 설정 (설정창에서 편집)
    FHotWnd: HWND;                  // 단축키 전용 숨은 윈도우 (폼 핸들 재생성과 무관)
    FHotId: Integer;
    FLastFollowUp: TDate;           // 팔로업 자동등록을 마지막으로 돌린 날짜
    FFollowFile: string;
    FFollowDone: TStringList;       // 이미 팔로업을 만든 캘린더 일정 UID 목록
    FLoading: Boolean;
    FReallyClose: Boolean;
    FLastFetch: TDateTime;
    FAlarmStack: Integer;
    FIcon: TIcon;
    FLastBackup: TDate;
    procedure ApplyCaptions;
    procedure ShutdownAll;
    procedure DoBackup(AManual: Boolean);
    procedure CleanOldBackups;
    procedure SetStartup(AEnable: Boolean);
    function IsStartupSet: Boolean;
    procedure CenterOnScreen;
    procedure BringUpFront;
    procedure ShowBriefing(AManual: Boolean);
    function BuildBriefingText: string;
    procedure CheckFollowUps;
    procedure BackupToDrive(AManual: Boolean);
    procedure ApplyHotKey;
    procedure ReleaseHotKey;
    procedure HotWndProc(var Msg: TMessage);
    function HotKeyVK: Word;
    procedure BuildIcon;
    procedure LoadCfg;
    procedure SaveCfg;
    procedure RefreshCalendarViews;
    procedure FetchGoogleTasks;
    procedure UpdateGoogleStatus;
    procedure RefreshTodo;
    procedure RefreshAlarm;
    function SelTodo: TTodoItem;
    function SelGoogleTask: TGoogleTask;
    procedure CollectTargets(ALocals: TList<TTodoItem>; AGoog: TList<TGoogleTask>);
    procedure AttachAlarmToNewest(const ATitle: string; ASrc: TTaskAlarm);
    function SelAlarm: TPcAlarm;
    procedure FireAlarm(const ATitle, AMent: string);
    procedure CheckAlarms;
  public
    /// 다른 폼(스케줄러)에서 트레이 풍선 알림을 띄울 때 사용
    procedure Notify(const ATitle, AText: string);
  end;

var
  frmDash: TfrmDash;

implementation

{$R *.dfm}

uses uMain;   // 카카오톡 스케줄러 폼

type
  { 내 할일 목록 정렬용 행 정보 }
  TTodoRow = record
    Grp: Integer;        // 0=오늘/미래, 1=지난일정, 2=기한없음
    SortDate: TDateTime;
    IsGoogle: Boolean;
    Local: TTodoItem;
    GTask: TGoogleTask;
  end;

var
  GDashCreated: Boolean = False;   // TfrmDash 가 이미 만들어졌는지 (중복 생성 차단용)

{ ---------- 시작프로그램 등록 ---------- }

const
  RUN_KEY   = 'Software\Microsoft\Windows\CurrentVersion\Run';
  RUN_VALUE = 'PlanManager';

function TfrmDash.IsStartupSet: Boolean;
var
  Reg: TRegistry;
begin
  Result := False;
  Reg := TRegistry.Create(KEY_READ);
  try
    Reg.RootKey := HKEY_CURRENT_USER;
    if Reg.OpenKeyReadOnly(RUN_KEY) then
      Result := Reg.ValueExists(RUN_VALUE);
  finally
    Reg.Free;
  end;
end;

procedure TfrmDash.SetStartup(AEnable: Boolean);
var
  Reg: TRegistry;
begin
  Reg := TRegistry.Create(KEY_READ or KEY_WRITE);
  try
    Reg.RootKey := HKEY_CURRENT_USER;
    if Reg.OpenKey(RUN_KEY, True) then
    begin
      if AEnable then
        // 부팅 시 실행 - 창을 중앙에 보이게(트레이 최소화 안 함)
        Reg.WriteString(RUN_VALUE, '"' + ParamStr(0) + '"')
      else if Reg.ValueExists(RUN_VALUE) then
        Reg.DeleteValue(RUN_VALUE);
    end;
  finally
    Reg.Free;
  end;
end;

procedure TfrmDash.chkStartupClick(Sender: TObject);
begin
  if FLoading then Exit;
  try
    SetStartup(chkStartup.Checked);
  except
    // 레지스트리 접근 실패는 무시
  end;
end;

procedure TfrmDash.CenterOnScreen;
begin
  // 현재 화면 작업영역 중앙에 배치 (Position 속성은 건드리지 않는다)
  Left := Screen.WorkAreaLeft + (Screen.WorkAreaWidth - Width) div 2;
  Top := Screen.WorkAreaTop + (Screen.WorkAreaHeight - Height) div 2;
end;

{
  창을 앞으로 가져온다.
  Show/Position 을 매번 건드리면 창이 재생성되며 깜빡이므로,
  이미 보이는 상태면 위치·표시 상태를 그대로 두고 포커스만 옮긴다.
}
procedure TfrmDash.BringUpFront;
var
  FgTid, MyTid: DWORD;
  WasHidden: Boolean;
begin
  if FDuplicate then Exit;

  WasHidden := (not Visible) or IsIconic(Handle);

  if IsIconic(Handle) then
    ShowWindow(Handle, SW_RESTORE)
  else if not Visible then
    ShowWindow(Handle, SW_SHOW);

  // 숨겨져 있다가 나타난 경우에만 중앙으로 재배치 (평소엔 위치 유지 = 깜빡임 없음)
  if WasHidden then
  begin
    if not Visible then Visible := True;
    CenterOnScreen;
  end;

  // 포커스 강제 이동 - 다른 스레드의 입력 큐에 붙여 정상적으로 전면 전환
  FgTid := GetWindowThreadProcessId(GetForegroundWindow, nil);
  MyTid := GetCurrentThreadId;
  if (FgTid <> 0) and (FgTid <> MyTid) then
  begin
    AttachThreadInput(MyTid, FgTid, True);
    try
      SetForegroundWindow(Handle);
      BringWindowToTop(Handle);
    finally
      AttachThreadInput(MyTid, FgTid, False);
    end;
  end
  else
    SetForegroundWindow(Handle);
end;

{ ---------- 전역 단축키 ----------
  폼(Handle)에 직접 등록하면 VCL 이 창 핸들을 다시 만들 때 등록이 풀린다.
  그래서 AllocateHWnd 로 만든 '절대 바뀌지 않는' 숨은 윈도우에 등록한다. }

function TfrmDash.HotKeyVK: Word;
var
  S: string;
  N: Integer;
begin
  Result := Ord('A');
  S := UpperCase(Trim(FSet.HotKeyName));
  if S = '' then Exit;
  if (Length(S) = 1) and (S[1] >= 'A') and (S[1] <= 'Z') then
    Result := Ord(S[1])
  else if (S[1] = 'F') and TryStrToInt(Copy(S, 2, 2), N) and (N >= 1) and (N <= 12) then
    Result := VK_F1 + N - 1;
end;

procedure TfrmDash.HotWndProc(var Msg: TMessage);
begin
  if (Msg.Msg = WM_HOTKEY) and (Msg.WParam = FHotId) then
    BringUpFront
  else
    Msg.Result := DefWindowProc(FHotWnd, Msg.Msg, Msg.WParam, Msg.LParam);
end;

procedure TfrmDash.ReleaseHotKey;
begin
  if (FHotWnd <> 0) and (FHotId <> 0) then
    UnregisterHotKey(FHotWnd, FHotId);
  FHotId := 0;
end;

procedure TfrmDash.ApplyHotKey;
var
  Mods: Cardinal;
begin
  ReleaseHotKey;
  if not FSet.HotOn then Exit;

  if FHotWnd = 0 then
    FHotWnd := AllocateHWnd(HotWndProc);
  if FHotWnd = 0 then Exit;

  Mods := 0;
  if FSet.HotCtrl then Mods := Mods or MOD_CONTROL;
  if FSet.HotAlt then Mods := Mods or MOD_ALT;
  if FSet.HotShift then Mods := Mods or MOD_SHIFT;
  if Mods = 0 then Exit;   // 조합 키 없이 단독 등록은 막는다

  FHotId := 1;
  if not RegisterHotKey(FHotWnd, FHotId, Mods, HotKeyVK) then
  begin
    FHotId := 0;
    Notify('단축키 등록 실패',
      '다른 프로그램이 같은 단축키를 쓰고 있습니다. 설정에서 조합을 바꿔보세요.');
  end;
end;

{ ---------- 오늘 브리핑 ---------- }

function TfrmDash.BuildBriefingText: string;
var
  SL: TStringList;
  Today: TDateTime;
  Ev: TCalEvent;
  It: TTodoItem;
  Tk: TGoogleTask;
  A: TTaskAlarm;
  CntCal, CntTodo: Integer;
begin
  SL := TStringList.Create;
  try
    Today := DateOf(Now);
    SL.Add(FormatDateTime('yyyy년 m월 d일 (ddd)', Today));
    SL.Add('');

    // 오늘 일정
    CntCal := 0;
    SL.Add('[오늘 일정]');
    if FCalCache <> nil then
      for Ev in FCalCache do
        if SameDate(Ev.StartTime, Today) then
        begin
          SL.Add('  · ' + Ev.TimeText + '  ' + Ev.Summary);
          Inc(CntCal);
        end;
    if CntCal = 0 then SL.Add('  (없음)');

    // 오늘 할일
    SL.Add('');
    SL.Add('[오늘 할일]');
    CntTodo := 0;
    for It in FTodos do
      if (not It.Done) and SameDate(It.RunDate, Today) then
      begin
        SL.Add('  · ' + FormatDateTime('hh:nn', It.RunTime) + '  ' + It.Title);
        Inc(CntTodo);
      end;
    if FGTasks <> nil then
      for Tk in FGTasks do
        if Tk.HasDue and SameDate(Tk.Due, Today) then
        begin
          A := FTaskAlarms.FindById(Tk.Id);
          if (A <> nil) and A.Alarm then
            SL.Add('  · ' + FormatDateTime('hh:nn', A.RunTime) + '  ' + Tk.Title)
          else
            SL.Add('  · ' + Tk.Title);
          Inc(CntTodo);
        end;
    if CntTodo = 0 then SL.Add('  (없음)');

    SL.Add('');
    SL.Add(Format('일정 %d건 / 할일 %d건', [CntCal, CntTodo]));
    Result := SL.Text;
  finally
    SL.Free;
  end;
end;

procedure TfrmDash.ShowBriefing(AManual: Boolean);
begin
  if FDuplicate then Exit;
  // 사이렌 없이 조용한 안내 팝업으로 표시 (멘트 복사 버튼으로 카톡에 붙여넣기 가능)
  TfrmAlarm.Popup('오늘 브리핑', BuildBriefingText, 0, False);
end;

procedure TfrmDash.miBriefClick(Sender: TObject);
begin
  ShowBriefing(True);
end;

{ ---------- 계약 후 팔로업 (내 할일 자동 등록) ---------- }

{
  캘린더 제목에서 고객명을 뽑아낸다.
  인정하는 형식 (둘 다 키워드로 끝나야 함):
    1) "<A> / <B> 출고"  - 슬래시가 있으면 회사 표기가 없는 쪽을 고객명으로
         "서승연 / 인허브 출고"         -> 서승연
         "주)스마트플래닝 / 박준호 출고" -> 박준호
         "으뜸피앤디(주) / 김이백 출고"  -> 김이백
    2) "<이름> 출고"     - 슬래시가 없으면 남은 부분 전체가 이름이어야 함
         "김이백 출고"                 -> 김이백
         "차경방문 28일 오전 출고"      -> (공백 포함 -> 제외)
  조건에 맞지 않으면 빈 문자열을 돌려주고, 그 일정은 건너뛴다.
}
function ExtractCustomerName(const ASummary, AKeyword: string): string;

  function LooksLikeCompany(const S: string): Boolean;
  const
    MARKS: array[0..5] of string =
      ('(주)', '주)', '㈜', '(유)', '주식회사', '(사)');
  var
    M: string;
  begin
    Result := False;
    for M in MARKS do
      if Pos(M, S) > 0 then
        Exit(True);
  end;

  // 사람 이름다운가: 공백 없는 한글 2~5자
  function LooksLikeName(const S: string): Boolean;
  var
    C: Char;
  begin
    Result := False;
    if (S.Length < 2) or (S.Length > 5) then Exit;
    for C in S do
      if (C < #$AC00) or (C > #$D7A3) then
        Exit(False);
    Result := True;
  end;

var
  T, L, R: string;
  P: Integer;
begin
  Result := '';
  T := Trim(ASummary);

  // 1) 반드시 키워드로 끝나야 한다 ("... 출고")
  if not T.EndsWith(AKeyword) then Exit;
  T := Trim(Copy(T, 1, T.Length - AKeyword.Length));
  if T = '' then Exit;

  P := Pos('/', T);
  if P > 0 then
  begin
    // --- 슬래시가 있는 경우: 회사 표기가 없는 쪽을 고객명으로 ---
    L := Trim(Copy(T, 1, P - 1));
    R := Trim(Copy(T, P + 1, MaxInt));
    if (L = '') or (R = '') then Exit;

    if LooksLikeCompany(L) and (not LooksLikeCompany(R)) then
      Result := R
    else if LooksLikeCompany(R) and (not LooksLikeCompany(L)) then
      Result := L
    else if LooksLikeName(L) then
      Result := L
    else if LooksLikeName(R) then
      Result := R
    else
      Result := L;
  end
  else
    // --- 슬래시가 없는 경우(개인/사업자 없음): 남은 부분 전체가 이름이어야 한다 ---
    Result := T;

  // 2) 최종적으로 사람 이름 형태가 아니면 등록하지 않는다
  if not LooksLikeName(Result) then
    Result := '';
end;

{
  구글 캘린더에서 "<고객명> / <업체> 출고" 형태의 일정을 찾아,
  출고일 + N개월 - 3일 날짜로 [내 할일]에 자동 등록한다.
  이미 등록한 일정은 UID 로 기록해 두 번 만들지 않는다.
}
procedure TfrmDash.CheckFollowUps;
var
  Ev: TCalEvent;
  Target: TDateTime;
  Name, Key, Ment: string;
  It: TTodoItem;
  Added: Integer;
begin
  if not FSet.FollowOn then Exit;
  if FCalCache = nil then Exit;
  if FLastFollowUp = Date then Exit;      // 하루 1회만 스캔
  FLastFollowUp := Date;

  Key := Trim(FSet.FollowKeyword);
  if Key = '' then Key := '출고';
  Added := 0;

  for Ev in FCalCache do
  begin
    if Ev.UID = '' then Continue;
    if FFollowDone.IndexOf(Ev.UID) >= 0 then Continue;   // 이미 처리함

    Name := ExtractCustomerName(Ev.Summary, Key);
    if Name = '' then Continue;                          // 형식에 안 맞으면 제외

    // 팔로업 날짜 = 출고일 + N개월, 그 3일 전에 등록/알림
    Target := IncMonth(DateOf(Ev.StartTime), FSet.FollowMonths) - 3;

    // 아직 등록할 때가 아니면 그냥 둔다 (다음 날 다시 검사해서 때가 되면 등록)
    if Target > Date then Continue;

    // 너무 오래 지난 건은 목록만 지저분해지므로 등록하지 않고 처리 완료로 기록
    if Target < Date - 14 then
    begin
      FFollowDone.Add(Ev.UID);
      Continue;
    end;

    Ment := FSet.FollowMent;
    if Pos('%s', Ment) > 0 then
      Ment := Format(Ment, [Name]);

    It := TTodoItem.Create;
    It.Title := Format('[팔로업] %s (%s %d개월)', [Name, Key, FSet.FollowMonths]);
    It.RunDate := Target;
    It.RunTime := FSet.FollowTime;
    It.HasTime := True;
    It.Alarm := FSet.FollowAlarm;
    It.Repeats := False;
    It.Ment := Ment + sLineBreak + sLineBreak +
      Format('(출고일: %s / 원 일정: %s)',
        [FormatDateTime('yyyy-mm-dd', Ev.StartTime), Ev.Summary]);
    FTodos.Add(It);

    FFollowDone.Add(Ev.UID);
    Inc(Added);
  end;

  if Added > 0 then
  begin
    FTodos.SaveToFile(FTodoFile);
    try
      FFollowDone.SaveToFile(FFollowFile, TEncoding.UTF8);
    except
    end;
    RefreshTodo;
    Notify('팔로업 자동 등록',
      Format('%d건을 [내 할일]에 추가했습니다.', [Added]));
  end;
end;

{ ---------- 구글 드라이브 백업 ---------- }

procedure TfrmDash.BackupToDrive(AManual: Boolean);
var
  Bundle: TJSONObject;
  Err, FName: string;

  function ReadIf(const AFile: string): TJSONValue;
  begin
    Result := nil;
    if FileExists(AFile) then
      try
        Result := TJSONObject.ParseJSONValue(TFile.ReadAllText(AFile, TEncoding.UTF8));
      except
        Result := nil;
      end;
  end;

  procedure AddPart(const AKey, AFile: string);
  var
    V: TJSONValue;
  begin
    V := ReadIf(AFile);
    if V <> nil then Bundle.AddPair(AKey, V);
  end;

begin
  if not FGAuth.IsConnected then
  begin
    if AManual then
      ShowMessage('구글에 로그인되어 있지 않습니다.' + sLineBreak +
        '[연동 설정] 에서 먼저 로그인하세요.');
    Exit;
  end;

  Bundle := TJSONObject.Create;
  try
    Bundle.AddPair('savedAt', FormatDateTime('yyyy-mm-dd hh:nn:ss', Now));
    AddPart('todos', FTodoFile);
    AddPart('pcalarms', FAlarmFile);
    AddPart('taskalarms', FTaskAlarmFile);
    AddPart('schedules', TPath.Combine(FDir, 'schedules.json'));
    AddPart('planCfg', FCfgFile);
    AddPart('kakaoCfg', TPath.Combine(FDir, 'config.json'));

    FName := 'PlanManager_backup_' + FormatDateTime('yyyymmdd_hhnnss', Now) + '.json';
    if TGoogleDrive.UploadText(FGAuth, FName, Bundle.ToJSON, Err) then
    begin
      if AManual then
        ShowMessage('구글 드라이브에 백업했습니다.' + sLineBreak + FName);
    end
    else if AManual then
      ShowMessage('드라이브 백업 실패:' + sLineBreak + Err);
  finally
    Bundle.Free;
  end;
end;

procedure TfrmDash.miDriveClick(Sender: TObject);
begin
  BackupToDrive(True);
end;

{ ---------- 자동 백업 ---------- }

procedure TfrmDash.DoBackup(AManual: Boolean);
var
  BkDir, Stamp, Src, Dst: string;
  Files: TArray<string>;
  F: string;
begin
  BkDir := TPath.Combine(FDir, 'backup');
  if not TDirectory.Exists(BkDir) then TDirectory.CreateDirectory(BkDir);

  Stamp := FormatDateTime('yyyymmdd_hhnnss', Now);

  // 대상: 할일 / PC알람 / 카톡예약 / 설정
  Files := [FTodoFile, FAlarmFile,
    TPath.Combine(FDir, 'schedules.json'),
    TPath.Combine(FDir, 'pcalarms.json'),
    TPath.Combine(FDir, 'todos.json'),
    TPath.Combine(FDir, 'taskalarms.json'),
    FCfgFile,
    TPath.Combine(FDir, 'config.json')];

  for F in Files do
    if FileExists(F) then
    begin
      Src := F;
      Dst := TPath.Combine(BkDir,
        Stamp + '_' + TPath.GetFileName(F));
      try
        TFile.Copy(Src, Dst, True);
      except
      end;
    end;

  FLastBackup := Date;
  CleanOldBackups;

  if AManual then
    ShowMessage('백업 완료: ' + BkDir);
end;

{ 30일 이상 지난 백업 파일 정리 }
procedure TfrmDash.CleanOldBackups;
var
  BkDir: string;
  Files: TArray<string>;
  F: string;
begin
  BkDir := TPath.Combine(FDir, 'backup');
  if not TDirectory.Exists(BkDir) then Exit;
  try
    Files := TDirectory.GetFiles(BkDir, '*.json');
    for F in Files do
      if DaysBetween(Now, TFile.GetLastWriteTime(F)) > 30 then
        TFile.Delete(F);
  except
  end;
end;

{ ---------- 캡션 (DFM 대신 코드에서 설정: 한글 인코딩 안전) ---------- }

procedure TfrmDash.ApplyCaptions;
  procedure Col(LV: TListView; const Names: array of string);
  var I: Integer;
  begin
    for I := 0 to High(Names) do
      if I < LV.Columns.Count then
        LV.Columns[I].Caption := Names[I];
  end;
begin
  lblApp.Caption := '일정관리기';
  btnScheduler.Caption := '카카오톡 스케줄러';
  chkStartup.Caption := 'PC 시작 시 실행';

  tsMain.Caption := '일정 / 할일';
  tsPcAlarm.Caption := 'PC 알람';

  btnSettings.Caption := '설정';
  btnFetch.Caption := '불러오기';
  chkAutoFetch.Caption := '30분 자동갱신';
  lblWeek.Caption := '이번주 일정';

  Col(lvWeek, ['날짜', '시각', '구분', '내용']);

  lblTodo.Caption := '내 할일';
  btnTodoAdd.Caption := '추가';
  btnTodoEdit.Caption := '수정';
  btnTodoDel.Caption := '삭제';
  btnTodoDone.Caption := '완료';
  btnTodoCopy.Caption := '멘트 복사';
  Col(lvTodo, ['선택', '날짜', '시각', '할일', '알람', '멘트']);

  btnAlAdd.Caption := '추가';
  btnAlEdit.Caption := '수정';
  btnAlDel.Caption := '삭제';
  btnAlTest.Caption := '미리보기';
  Col(lvAlarm, ['사용', '이름', '요일', '시각', '멘트']);

  miShow.Caption := '창 열기';
  miScheduler.Caption := '카카오톡 스케줄러';
  miBrief.Caption := '오늘 브리핑';
  miBackup.Caption := '지금 백업 (로컬)';
  miDrive.Caption := '구글 드라이브 백업';
  miDiag.Caption := '진단 정보';
  miExit.Caption := '종료';
end;

{ ---------- 트레이 아이콘 ---------- }

procedure TfrmDash.BuildIcon;
var
  IcoPath: string;
begin
  FIcon := TIcon.Create;
  IcoPath := TPath.Combine(ExtractFilePath(ParamStr(0)), 'PlanManager.ico');
  try
    if FileExists(IcoPath) then
      FIcon.LoadFromFile(IcoPath)          // 실행파일과 같은 폴더의 아이콘
    else
      FIcon.Assign(Application.Icon);       // 없으면 기본 아이콘
  except
    FIcon.Assign(Application.Icon);
  end;
  if not FIcon.Empty then
    Application.Icon.Assign(FIcon);
  TrayIcon1.Icon.Assign(FIcon);
  TrayIcon1.Visible := True;
end;

{ ---------- 초기화 ---------- }

procedure TfrmDash.FormCreate(Sender: TObject);
begin
  // 프로젝트 설정 문제 등으로 이 폼이 두 번 생성되면, 두 번째는 완전히 무력화한다.
  // (트레이 아이콘·창이 2개씩 뜨는 것을 원천 차단)
  if GDashCreated then
  begin
    FDuplicate := True;
    FLoading := True;          // 타이머 내용이 절대 실행되지 않도록
    Timer1.Enabled := False;
    TrayIcon1.Visible := False;
    Visible := False;
    Exit;
  end;
  GDashCreated := True;
  FDuplicate := False;

  FLoading := True;
  FReallyClose := False;
  FAlarmStack := 0;

  FDir := TPath.Combine(TPath.GetHomePath, 'KakaoScheduler');
  if not TDirectory.Exists(FDir) then TDirectory.CreateDirectory(FDir);
  FTodoFile := TPath.Combine(FDir, 'todos.json');
  FAlarmFile := TPath.Combine(FDir, 'pcalarms.json');
  FTaskAlarmFile := TPath.Combine(FDir, 'taskalarms.json');
  FFollowFile := TPath.Combine(FDir, 'followups.json');
  FCfgFile := TPath.Combine(FDir, 'plan_cfg.json');

  BuildIcon;
  TrayIcon1.Hint := '일정관리기';

  Caption := '일정관리기';
  ApplyCaptions;

  FTodos := TTodoList.Create(True);
  FAlarms := TPcAlarmList.Create(True);
  FTaskAlarms := TTaskAlarmList.Create(True);
  FFollowDone := TStringList.Create;
  FFollowDone.Sorted := True;
  FFollowDone.Duplicates := dupIgnore;
  FCalCache := nil;
  FGTasks := nil;
  FWeekDates := TList<TDateTime>.Create;
  FTodoDates := TList<TDateTime>.Create;
  FGAuth := TGoogleAuth.Create(TPath.Combine(FDir, 'google_oauth.json'));

  try FTodos.LoadFromFile(FTodoFile); except end;
  try FAlarms.LoadFromFile(FAlarmFile); except end;
  try FTaskAlarms.LoadFromFile(FTaskAlarmFile); except end;
  try
    if FileExists(FFollowFile) then
      FFollowDone.LoadFromFile(FFollowFile, TEncoding.UTF8);
  except
  end;

  LoadCfg;
  RefreshTodo;
  RefreshAlarm;

  FLoading := False;

  // 하루 1회 자동 백업 (오늘 아직 안 했으면)
  FLastBackup := 0;
  DoBackup(False);

  // 카카오톡 스케줄러 폼을 미리(숨김) 생성해 둔다.
  // 그래야 창을 열지 않아도 예약 발송 타이머가 백그라운드에서 동작한다.
  // Application.CreateForm 을 쓰면 메인 폼이 뒤바뀔 수 있으므로 일반 생성한다.
  if frmMain = nil then
  begin
    frmMain := TfrmMain.Create(Application);
    // 작업표시줄에 별도 버튼이 생기지 않도록 처리 (아이콘 2개 방지)
    SetWindowLong(frmMain.Handle, GWL_EXSTYLE,
      GetWindowLong(frmMain.Handle, GWL_EXSTYLE) or WS_EX_TOOLWINDOW);
    frmMain.Hide;
  end;

  // ICS 주소가 있으면 시작 시 한 번 자동으로 불러온다
  if Trim(FSet.CalUrl) <> '' then
    btnFetchClick(nil);

  // 구글 Tasks: 연결돼 있으면 시작 시 불러오기
  UpdateGoogleStatus;
  if FGAuth.IsConnected then
    FetchGoogleTasks;

  // 시작프로그램 등록 상태를 체크박스에 반영
  chkStartup.Checked := IsStartupSet;

  // 이전 버전(스케줄러)이 남긴 시작 항목이 있으면 정리하고,
  // 시작 등록이 켜져 있으면 현재 exe 경로로 다시 써서 경로 불일치를 막는다
  try
    with TRegistry.Create(KEY_READ or KEY_WRITE) do
    try
      RootKey := HKEY_CURRENT_USER;
      if OpenKey(RUN_KEY, False) then
      begin
        if ValueExists('KakaoScheduler') then
          DeleteValue('KakaoScheduler');
        // PlanManager 항목이 있으면(=시작 등록 상태) 현재 exe 경로로 갱신
        if ValueExists(RUN_VALUE) then
          WriteString(RUN_VALUE, '"' + ParamStr(0) + '"');
      end;
    finally
      Free;
    end;
  except
  end;

  // 전역 단축키 등록 (설정값 기준)
  FHotWnd := 0;
  FHotId := 0;
  ApplyHotKey;

  FBootTicks := 0;
  FLastFollowUp := 0;

  // 팔로업 자동 등록 (캘린더를 이미 불러온 뒤이므로 바로 스캔)
  CheckFollowUps;

  // /tray 스위치로 실행되면 트레이로, 아니면(부팅 포함) 화면 중앙에 표시
  if FindCmdLineSwitch('tray', ['/', '-'], True) then
  begin
    Hide;
    Application.ShowMainForm := False;
  end
  else
  begin
    CenterOnScreen;
    // 부팅 직후에는 다른 창이 포커스를 뺏을 수 있어 잠시 뒤 다시 끌어올린다
    FBootTicks := 1;
  end;

  // 시작 시 오늘 브리핑 (트레이 시작이 아닐 때만)
  if FBootTicks > 0 then
    ShowBriefing(False);
end;

procedure TfrmDash.FormDestroy(Sender: TObject);
begin
  if FDuplicate then Exit;   // 중복 인스턴스는 초기화된 게 없으므로 정리도 하지 않는다
  ReleaseHotKey;
  if FHotWnd <> 0 then
  begin
    DeallocateHWnd(FHotWnd);
    FHotWnd := 0;
  end;
  SaveCfg;
  FTodos.Free;
  FAlarms.Free;
  FTaskAlarms.Free;
  FFollowDone.Free;
  FCalCache.Free;
  FGTasks.Free;
  FGAuth.Free;
  FWeekDates.Free;
  FTodoDates.Free;
  FIcon.Free;
end;

{ ---------- 설정 ---------- }

procedure TfrmDash.LoadCfg;
var
  V: TJSONValue;
  O: TJSONObject;
  FS: TFormatSettings;
  T: TDateTime;
begin
  FSet.SetDefaults;
  if not FileExists(FCfgFile) then Exit;

  FS := TFormatSettings.Invariant;
  FS.TimeSeparator := ':';
  FS.ShortTimeFormat := 'hh:nn';

  V := nil;
  try
    V := TJSONObject.ParseJSONValue(TFile.ReadAllText(FCfgFile, TEncoding.UTF8));
    if V is TJSONObject then
    begin
      O := TJSONObject(V);
      FSet.CalUrl          := O.GetValue<string>('calUrl', '');
      chkAutoFetch.Checked := O.GetValue<Boolean>('autoFetch', False);

      FSet.FollowOn      := O.GetValue<Boolean>('followOn', True);
      FSet.FollowKeyword := O.GetValue<string>('followKeyword', '출고');
      FSet.FollowMonths  := O.GetValue<Integer>('followMonths', 1);
      FSet.FollowAlarm   := O.GetValue<Boolean>('followAlarm', True);
      FSet.FollowMent    := O.GetValue<string>('followMent', DEF_FOLLOW_MENT);
      if TryStrToTime(O.GetValue<string>('followTime', '10:00'), T, FS) then
        FSet.FollowTime := T;

      FSet.HotOn      := O.GetValue<Boolean>('hotOn', True);
      FSet.HotCtrl    := O.GetValue<Boolean>('hotCtrl', True);
      FSet.HotAlt     := O.GetValue<Boolean>('hotAlt', True);
      FSet.HotShift   := O.GetValue<Boolean>('hotShift', False);
      FSet.HotKeyName := O.GetValue<string>('hotKey', 'A');
    end;
  except
  end;
  V.Free;
end;

procedure TfrmDash.SaveCfg;
var
  O: TJSONObject;
begin
  O := TJSONObject.Create;
  try
    O.AddPair('calUrl', Trim(FSet.CalUrl));
    O.AddPair('autoFetch', TJSONBool.Create(chkAutoFetch.Checked));

    O.AddPair('followOn', TJSONBool.Create(FSet.FollowOn));
    O.AddPair('followKeyword', FSet.FollowKeyword);
    O.AddPair('followMonths', TJSONNumber.Create(FSet.FollowMonths));
    O.AddPair('followAlarm', TJSONBool.Create(FSet.FollowAlarm));
    O.AddPair('followTime', FormatDateTime('hh:nn', FSet.FollowTime));
    O.AddPair('followMent', FSet.FollowMent);

    O.AddPair('hotOn', TJSONBool.Create(FSet.HotOn));
    O.AddPair('hotCtrl', TJSONBool.Create(FSet.HotCtrl));
    O.AddPair('hotAlt', TJSONBool.Create(FSet.HotAlt));
    O.AddPair('hotShift', TJSONBool.Create(FSet.HotShift));
    O.AddPair('hotKey', FSet.HotKeyName);

    TFile.WriteAllText(FCfgFile, O.ToJSON, TEncoding.UTF8);
  except
  end;
  O.Free;
end;

{ ---------- 캘린더 ---------- }

procedure TfrmDash.btnFetchClick(Sender: TObject);
var
  Err: string;
  New: TCalEventList;
begin
  if Trim(FSet.CalUrl) = '' then
  begin
    ShowMessage('구글 캘린더 ICS 주소를 입력하세요.' + sLineBreak +
      '(구글 캘린더 → 설정 → 해당 캘린더 → "비공개 주소(iCal 형식)")');
    Exit;
  end;

  btnFetch.Enabled := False;
  btnFetch.Caption := '불러오는 중...';
  Application.ProcessMessages;
  try
    New := TCalendarFetcher.Fetch(FSet.CalUrl, Err);
    if New = nil then
    begin
      ShowMessage('캘린더를 불러오지 못했습니다.' + sLineBreak + Err);
      Exit;
    end;
    FCalCache.Free;
    FCalCache := New;
    FLastFetch := Now;
    RefreshCalendarViews;
    SaveCfg;
  finally
    btnFetch.Enabled := True;
    btnSettings.Caption := '설정';
  btnFetch.Caption := '불러오기';
  end;
end;

{ ---------- 구글 Tasks ---------- }

procedure TfrmDash.UpdateGoogleStatus;
begin
  if FGAuth.ClientId = '' then
  begin
    lblGStatus.Caption := '구글 Tasks: 미설정 ([연동 설정]에서 등록)';
    lblGStatus.Font.Color := clGrayText;
  end
  else if FGAuth.IsConnected then
  begin
    lblGStatus.Caption := '구글 Tasks: 연결됨';
    lblGStatus.Font.Color := clGreen;
  end
  else
  begin
    lblGStatus.Caption := '구글 Tasks: 로그인 필요';
    lblGStatus.Font.Color := clRed;
  end;
end;

{ 연동 설정 창 - ICS 주소 / 구글 Tasks 로그인을 한곳에서 관리 }
procedure TfrmDash.btnSettingsClick(Sender: TObject);
var
  TasksChanged: Boolean;
begin
  if TfrmGSettings.Edit(FGAuth, FSet, TasksChanged) then
  begin
    SaveCfg;
    ApplyHotKey;                 // 단축키 변경 즉시 반영
    FLastFollowUp := 0;          // 설정이 바뀌었으니 팔로업 다시 스캔
    if Trim(FSet.CalUrl) <> '' then
      btnFetchClick(nil);
    CheckFollowUps;
  end;

  // 로그인/로그아웃이 있었으면 할일 목록 갱신
  if TasksChanged then
  begin
    if FGAuth.IsConnected then
      FetchGoogleTasks
    else
    begin
      FreeAndNil(FGTasks);
      RefreshTodo;
    end;
  end;
  UpdateGoogleStatus;
end;

procedure TfrmDash.FetchGoogleTasks;
var
  Err: string;
  New: TGoogleTaskList;
begin
  if not FGAuth.IsConnected then Exit;
  New := TGoogleTasksFetcher.FetchAll(FGAuth, Err);
  if New = nil then Exit;
  if (Err <> '') and (New.Count = 0) then
  begin
    // 오류지만 조용히 로그만 (팝업 남발 방지). 상태만 갱신.
    New.Free;
    UpdateGoogleStatus;
    Exit;
  end;
  FGTasks.Free;
  FGTasks := New;
  RefreshTodo;
end;

procedure TfrmDash.RefreshCalendarViews;
var
  Today, WeekEnd: TDateTime;
  Ev: TCalEvent;
  LI: TListItem;
begin
  lvWeek.Items.Clear;
  FWeekDates.Clear;

  Today := DateOf(Now);
  WeekEnd := Today + 7;

  // 이번주 뷰에는 구글 캘린더 일정만 표시 (구글 Tasks 는 하단 '내 할일'로)
  if FCalCache <> nil then
    for Ev in FCalCache do
      if (Ev.StartTime >= Today) and (Ev.StartTime < WeekEnd) then
      begin
        LI := lvWeek.Items.Add;
        LI.Caption := FormatDateTime('mm-dd(ddd)', Ev.StartTime);
        LI.SubItems.Add(Ev.TimeText);
        LI.SubItems.Add('일정');
        LI.SubItems.Add(Ev.Summary);
        FWeekDates.Add(DateOf(Ev.StartTime));
      end;

  lblWeek.Caption := Format('이번주 일정  %d건', [lvWeek.Items.Count]);
end;

{ 오늘=주황, 내일=노랑으로 한 줄 강조 }
procedure TfrmDash.lvWeekCustomDrawItem(Sender: TCustomListView;
  Item: TListItem; State: TCustomDrawState; var DefaultDraw: Boolean);
var
  D, Today: TDateTime;
begin
  DefaultDraw := True;
  if (Item.Index < 0) or (Item.Index >= FWeekDates.Count) then Exit;
  D := FWeekDates[Item.Index];
  Today := DateOf(Now);

  if SameDate(D, Today) then
  begin
    Sender.Canvas.Brush.Color := $0060A8FF;   // 주황(오늘)
    Sender.Canvas.Font.Style := [fsBold];
  end
  else if SameDate(D, Today + 1) then
  begin
    Sender.Canvas.Brush.Color := $0080FFFF;   // 노랑(내일)
    Sender.Canvas.Font.Style := [fsBold];
  end
  else
  begin
    Sender.Canvas.Brush.Color := clWindow;
    Sender.Canvas.Font.Style := [];
  end;
end;

{ ---------- 할일 ---------- }

{ 내 할일: 오늘=주황, 내일=노랑 강조 }
procedure TfrmDash.lvTodoCustomDrawItem(Sender: TCustomListView;
  Item: TListItem; State: TCustomDrawState; var DefaultDraw: Boolean);
var
  D, Today: TDateTime;
begin
  DefaultDraw := True;
  if (Item.Index < 0) or (Item.Index >= FTodoDates.Count) then Exit;
  D := FTodoDates[Item.Index];
  if D = 0 then
  begin
    Sender.Canvas.Brush.Color := clWindow;
    Sender.Canvas.Font.Style := [];
    Exit;
  end;
  Today := DateOf(Now);

  if SameDate(D, Today) then
  begin
    Sender.Canvas.Brush.Color := $0060A8FF;   // 주황(오늘)
    Sender.Canvas.Font.Style := [fsBold];
  end
  else if SameDate(D, Today + 1) then
  begin
    Sender.Canvas.Brush.Color := $0080FFFF;   // 노랑(내일)
    Sender.Canvas.Font.Style := [fsBold];
  end
  else
  begin
    Sender.Canvas.Brush.Color := clWindow;
    Sender.Canvas.Font.Style := [];
  end;
end;

procedure TfrmDash.RefreshTodo;
var
  It: TTodoItem;
  Tk: TGoogleTask;
  A: TTaskAlarm;
  LI: TListItem;
  Idx, I: Integer;
  Rows: TList<TTodoRow>;
  R: TTodoRow;
  Today: TDateTime;

  { 날짜에 따라 정렬 그룹을 정한다 }
  procedure FillGroup(var ARow: TTodoRow; AHasDue: Boolean; ADue: TDateTime);
  begin
    if not AHasDue then
    begin
      ARow.Grp := 2;               // 기한없음 -> 맨 아래
      ARow.SortDate := 0;
    end
    else if DateOf(ADue) >= Today then
    begin
      ARow.Grp := 0;               // 오늘/미래 -> 맨 위
      ARow.SortDate := DateOf(ADue);
    end
    else
    begin
      ARow.Grp := 1;               // 지난 일정 -> 중간
      ARow.SortDate := DateOf(ADue);
    end;
  end;

begin
  Idx := lvTodo.ItemIndex;
  Today := DateOf(Now);
  Rows := TList<TTodoRow>.Create;
  lvTodo.Items.BeginUpdate;
  try
    lvTodo.Items.Clear;
    FTodoDates.Clear;

    // 1) 로컬 할일 수집 (지난 일정은 7일 이내만)
    for It in FTodos do
    begin
      if DateOf(It.RunDate) < Today - 7 then Continue;
      R.IsGoogle := False;
      R.Local := It;
      R.GTask := nil;
      FillGroup(R, True, It.RunDate);
      Rows.Add(R);
    end;

    // 2) 구글 Tasks 수집 (기한 없는 것 포함, 지난 기한은 7일 이내만)
    if FGTasks <> nil then
      for Tk in FGTasks do
      begin
        if Tk.HasDue and (DateOf(Tk.Due) < Today - 7) then Continue;
        R.IsGoogle := True;
        R.Local := nil;
        R.GTask := Tk;
        FillGroup(R, Tk.HasDue, Tk.Due);
        Rows.Add(R);
      end;

    // 3) 정렬: 오늘/미래(가까운 날짜부터) -> 지난일정(최근부터) -> 기한없음
    Rows.Sort(TComparer<TTodoRow>.Construct(
      function(const X, Y: TTodoRow): Integer
      begin
        Result := X.Grp - Y.Grp;
        if Result <> 0 then Exit;
        case X.Grp of
          0: Result := CompareDateTime(X.SortDate, Y.SortDate);   // 오름차순
          1: Result := CompareDateTime(Y.SortDate, X.SortDate);   // 내림차순(최근 과거 우선)
        else
          Result := 0;
        end;
      end));

    // 4) 화면에 채우기
    for I := 0 to Rows.Count - 1 do
    begin
      R := Rows[I];
      LI := lvTodo.Items.Add;

      if not R.IsGoogle then
      begin
        It := R.Local;
        LI.Caption := '';   // 체크박스 칸
        LI.SubItems.Add(It.DaysText);
        LI.SubItems.Add(IfThen(It.HasTime, FormatDateTime('hh:nn', It.RunTime), '-'));
        LI.SubItems.Add(IfThen(It.Done, '[완료] ', '') + It.Title);
        LI.SubItems.Add(IfThen(It.Alarm, 'ON', ''));
        LI.SubItems.Add(Copy(StringReplace(It.Ment, sLineBreak, ' ', [rfReplaceAll]), 1, 60));
        LI.Data := It;
        FTodoDates.Add(DateOf(It.RunDate));
      end
      else
      begin
        Tk := R.GTask;
        A := FTaskAlarms.FindById(Tk.Id);
        LI.Caption := '';
        if Tk.HasDue then
          LI.SubItems.Add(FormatDateTime('mm-dd(ddd)', Tk.Due))
        else
          LI.SubItems.Add('기한없음');
        if (A <> nil) and A.Alarm then
          LI.SubItems.Add(FormatDateTime('hh:nn', A.RunTime))
        else
          LI.SubItems.Add('-');
        LI.SubItems.Add('[구글] ' + Tk.Title);
        if (A <> nil) and A.Alarm then
          LI.SubItems.Add('ON')
        else
          LI.SubItems.Add('');
        if (A <> nil) and (Trim(A.Ment) <> '') then
          LI.SubItems.Add(Copy(StringReplace(A.Ment, sLineBreak, ' ', [rfReplaceAll]), 1, 60))
        else
          LI.SubItems.Add(Copy(StringReplace(Tk.Notes, sLineBreak, ' ', [rfReplaceAll]), 1, 60));
        LI.Data := Tk;
        if Tk.HasDue then
          FTodoDates.Add(DateOf(Tk.Due))
        else
          FTodoDates.Add(0);
      end;
    end;
  finally
    lvTodo.Items.EndUpdate;
    Rows.Free;
  end;
  if (Idx >= 0) and (Idx < lvTodo.Items.Count) then
    lvTodo.ItemIndex := Idx;
end;

function TfrmDash.SelTodo: TTodoItem;
var
  P: Pointer;
begin
  Result := nil;
  if lvTodo.Selected = nil then Exit;
  P := lvTodo.Selected.Data;
  // Data 가 로컬 할일 목록에 실제로 있을 때만 반환 (구글 항목 배제)
  if (P <> nil) and (FTodos.IndexOf(TTodoItem(P)) >= 0) then
    Result := TTodoItem(P);
end;

function TfrmDash.SelGoogleTask: TGoogleTask;
var
  P: Pointer;
begin
  Result := nil;
  if (lvTodo.Selected = nil) or (FGTasks = nil) then Exit;
  P := lvTodo.Selected.Data;
  if (P <> nil) and (FGTasks.IndexOf(TGoogleTask(P)) >= 0) then
    Result := TGoogleTask(P);
end;

procedure TfrmDash.btnTodoAddClick(Sender: TObject);
var
  It: TTodoItem;
  Title, Notes, Err: string;
  Due: TDateTime;
  HasDue: Boolean;
  Tmp: TTaskAlarm;
begin
  // 구글이 연결돼 있으면 구글 Tasks 에만 등록한다 (중복 생성 방지).
  // 알람 설정은 task id 에 매핑해 로컬에 따로 보관.
  if FGAuth.IsConnected then
  begin
    Title := '';
    Notes := '';
    Due := Date;
    HasDue := True;
    Tmp := TTaskAlarm.Create;
    try
      if not TfrmPlanEdit.EditGoogleTask('할일 추가 (구글 Tasks)',
        Title, Notes, Due, HasDue, Tmp) then Exit;
      if Trim(Title) = '' then Exit;

      if not HasDue then Due := 0;
      if not TGoogleTasksFetcher.InsertTask(FGAuth, '', Title, Notes, Due, Err) then
      begin
        ShowMessage('구글 할일 추가 실패:' + sLineBreak + Err);
        Exit;
      end;

      // 새로 만든 항목의 id 를 알기 위해 목록을 다시 받아온 뒤 매핑 저장
      FetchGoogleTasks;
      if Tmp.Alarm or (Trim(Tmp.Ment) <> '') then
        AttachAlarmToNewest(Title, Tmp);
    finally
      Tmp.Free;
    end;
    Exit;
  end;

  // 구글 미연결 시에는 기존처럼 로컬 할일로 저장
  It := TTodoItem.Create;
  if TfrmPlanEdit.EditTodo(It) then
  begin
    FTodos.Add(It);
    FTodos.SaveToFile(FTodoFile);
    RefreshTodo;
  end
  else
    It.Free;
end;

{ 방금 만든 구글 항목(제목이 같은 것)에 알람 설정을 붙인다 }
procedure TfrmDash.AttachAlarmToNewest(const ATitle: string; ASrc: TTaskAlarm);
var
  Tk, Found: TGoogleTask;
  A: TTaskAlarm;
begin
  if FGTasks = nil then Exit;
  Found := nil;
  for Tk in FGTasks do
    if Tk.Title = ATitle then
      Found := Tk;          // 동명이 여럿이면 마지막(가장 최근) 것
  if Found = nil then Exit;

  A := FTaskAlarms.EnsureById(Found.Id);
  A.Alarm := ASrc.Alarm;
  A.RunTime := ASrc.RunTime;
  A.Ment := ASrc.Ment;
  FTaskAlarms.SaveToFile(FTaskAlarmFile);
  RefreshTodo;
end;

procedure TfrmDash.btnTodoEditClick(Sender: TObject);
var
  It: TTodoItem;
  Gt: TGoogleTask;
  A: TTaskAlarm;
  Title, Notes, Err: string;
  Due: TDateTime;
  HasDue: Boolean;
begin
  // 1) 구글 Tasks 항목 수정
  Gt := SelGoogleTask;
  if Gt <> nil then
  begin
    Title := Gt.Title;
    Notes := Gt.Notes;
    Due := Gt.Due;
    HasDue := Gt.HasDue;
    A := FTaskAlarms.EnsureById(Gt.Id);

    if not TfrmPlanEdit.EditGoogleTask('할일 수정 (구글 Tasks)',
      Title, Notes, Due, HasDue, A) then Exit;
    if Trim(Title) = '' then Exit;

    if TGoogleTasksFetcher.UpdateTask(FGAuth, Gt.ListId, Gt.Id,
      Title, Notes, Due, HasDue, Err) then
    begin
      FTaskAlarms.SaveToFile(FTaskAlarmFile);
      FetchGoogleTasks;
    end
    else
      ShowMessage('구글 수정 실패:' + sLineBreak + Err);
    Exit;
  end;

  // 2) 로컬 할일 수정
  It := SelTodo;
  if It = nil then
  begin
    ShowMessage('수정할 할일을 선택하세요.');
    Exit;
  end;
  if TfrmPlanEdit.EditTodo(It) then
  begin
    FTodos.SaveToFile(FTodoFile);
    RefreshTodo;
  end;
end;

procedure TfrmDash.lvTodoDblClick(Sender: TObject);
begin
  btnTodoEditClick(nil);
end;

{ 체크된 항목을 모은다. 하나도 체크 안 됐으면 현재 선택 행을 대상으로 한다. }
procedure TfrmDash.CollectTargets(ALocals: TList<TTodoItem>; AGoog: TList<TGoogleTask>);
var
  I: Integer;
  P: Pointer;
  AnyChecked: Boolean;

  procedure AddByData(AData: Pointer);
  begin
    if AData = nil then Exit;
    if FTodos.IndexOf(TTodoItem(AData)) >= 0 then
      ALocals.Add(TTodoItem(AData))
    else if (FGTasks <> nil) and (FGTasks.IndexOf(TGoogleTask(AData)) >= 0) then
      AGoog.Add(TGoogleTask(AData));
  end;

begin
  AnyChecked := False;
  for I := 0 to lvTodo.Items.Count - 1 do
    if lvTodo.Items[I].Checked then
    begin
      AnyChecked := True;
      AddByData(lvTodo.Items[I].Data);
    end;

  if not AnyChecked then
    if lvTodo.Selected <> nil then
      AddByData(lvTodo.Selected.Data);
end;

procedure TfrmDash.btnTodoDelClick(Sender: TObject);
var
  I, CntG, Fail: Integer;
  Locals: TList<TTodoItem>;
  Goog: TList<TGoogleTask>;
  A: TTaskAlarm;
  Err: string;
begin
  Locals := TList<TTodoItem>.Create;
  Goog := TList<TGoogleTask>.Create;
  try
    CollectTargets(Locals, Goog);
    if (Locals.Count = 0) and (Goog.Count = 0) then
    begin
      ShowMessage('삭제할 항목을 체크하거나 선택하세요.');
      Exit;
    end;

    if MessageDlg(Format('%d건을 삭제할까요?' + sLineBreak +
      '(구글 항목은 구글 Tasks 에서도 삭제됩니다)',
      [Locals.Count + Goog.Count]), mtConfirmation, [mbYes, mbNo], 0) <> mrYes then Exit;

    CntG := 0; Fail := 0;
    for I := 0 to Goog.Count - 1 do
      if TGoogleTasksFetcher.DeleteTask(FGAuth, Goog[I].ListId, Goog[I].Id, Err) then
      begin
        A := FTaskAlarms.FindById(Goog[I].Id);
        if A <> nil then FTaskAlarms.Remove(A);
        Inc(CntG);
      end
      else
        Inc(Fail);
    if CntG > 0 then FTaskAlarms.SaveToFile(FTaskAlarmFile);

    for I := 0 to Locals.Count - 1 do
      FTodos.Remove(Locals[I]);
    if Locals.Count > 0 then FTodos.SaveToFile(FTodoFile);

    if CntG > 0 then FetchGoogleTasks else RefreshTodo;

    if Fail > 0 then
      ShowMessage(Format('%d건은 삭제하지 못했습니다.' + sLineBreak + '%s', [Fail, Err]));
  finally
    Locals.Free;
    Goog.Free;
  end;
end;

procedure TfrmDash.btnTodoDoneClick(Sender: TObject);
var
  I, CntG, Fail: Integer;
  Locals: TList<TTodoItem>;
  Goog: TList<TGoogleTask>;
  Err: string;
begin
  Locals := TList<TTodoItem>.Create;
  Goog := TList<TGoogleTask>.Create;
  try
    CollectTargets(Locals, Goog);
    if (Locals.Count = 0) and (Goog.Count = 0) then
    begin
      ShowMessage('완료 처리할 항목을 체크하거나 선택하세요.');
      Exit;
    end;

    // 구글 항목이 섞여 있으면 되돌릴 수 없으므로 확인
    if Goog.Count > 0 then
      if MessageDlg(Format('%d건을 완료 처리할까요?' + sLineBreak +
        '(구글 항목 %d건은 목록에서 사라집니다)',
        [Locals.Count + Goog.Count, Goog.Count]),
        mtConfirmation, [mbYes, mbNo], 0) <> mrYes then Exit;

    for I := 0 to Locals.Count - 1 do
      Locals[I].Done := not Locals[I].Done;
    if Locals.Count > 0 then FTodos.SaveToFile(FTodoFile);

    CntG := 0; Fail := 0;
    for I := 0 to Goog.Count - 1 do
      if TGoogleTasksFetcher.CompleteTask(FGAuth, Goog[I].ListId, Goog[I].Id, Err) then
        Inc(CntG)
      else
        Inc(Fail);

    if CntG > 0 then FetchGoogleTasks else RefreshTodo;

    if Fail > 0 then
      ShowMessage(Format('%d건은 처리하지 못했습니다.' + sLineBreak + '%s', [Fail, Err]));
  finally
    Locals.Free;
    Goog.Free;
  end;
end;

procedure TfrmDash.btnTodoCopyClick(Sender: TObject);
var
  It: TTodoItem;
begin
  It := SelTodo;
  if It = nil then Exit;
  if Trim(It.Ment) = '' then
  begin
    ShowMessage('이 할일에는 저장된 멘트가 없습니다.');
    Exit;
  end;
  Clipboard.AsText := It.Ment;
  ShowMessage('멘트를 복사했습니다. 카톡에 붙여넣으세요.');
end;

{ ---------- PC 알람 ---------- }

procedure TfrmDash.RefreshAlarm;
var
  It: TPcAlarm;
  LI: TListItem;
  Idx: Integer;
begin
  Idx := lvAlarm.ItemIndex;
  lvAlarm.Items.BeginUpdate;
  try
    lvAlarm.Items.Clear;
    for It in FAlarms do
    begin
      LI := lvAlarm.Items.Add;
      LI.Caption := IfThen(It.Enabled, 'ON', 'OFF');
      LI.SubItems.Add(It.Title);
      LI.SubItems.Add(It.DaysText);
      LI.SubItems.Add(FormatDateTime('hh:nn', It.RunTime));
      LI.SubItems.Add(Copy(StringReplace(It.Ment, sLineBreak, ' ', [rfReplaceAll]), 1, 80));
      LI.Data := It;
    end;
  finally
    lvAlarm.Items.EndUpdate;
  end;
  if (Idx >= 0) and (Idx < lvAlarm.Items.Count) then
    lvAlarm.ItemIndex := Idx;
end;

function TfrmDash.SelAlarm: TPcAlarm;
begin
  Result := nil;
  if lvAlarm.Selected <> nil then
    Result := TPcAlarm(lvAlarm.Selected.Data);
end;

procedure TfrmDash.btnAlAddClick(Sender: TObject);
var
  It: TPcAlarm;
begin
  It := TPcAlarm.Create;
  if TfrmPlanEdit.EditAlarm(It) then
  begin
    FAlarms.Add(It);
    FAlarms.SaveToFile(FAlarmFile);
    RefreshAlarm;
  end
  else
    It.Free;
end;

procedure TfrmDash.btnAlEditClick(Sender: TObject);
var
  It: TPcAlarm;
begin
  It := SelAlarm;
  if It = nil then Exit;
  if TfrmPlanEdit.EditAlarm(It) then
  begin
    FAlarms.SaveToFile(FAlarmFile);
    RefreshAlarm;
  end;
end;

procedure TfrmDash.lvAlarmDblClick(Sender: TObject);
begin
  btnAlEditClick(nil);
end;

procedure TfrmDash.btnAlDelClick(Sender: TObject);
var
  It: TPcAlarm;
begin
  It := SelAlarm;
  if It = nil then Exit;
  if MessageDlg('이 알람을 삭제할까요?', mtConfirmation, [mbYes, mbNo], 0) <> mrYes then Exit;
  FAlarms.Remove(It);
  FAlarms.SaveToFile(FAlarmFile);
  RefreshAlarm;
end;

procedure TfrmDash.btnAlTestClick(Sender: TObject);
var
  It: TPcAlarm;
begin
  It := SelAlarm;
  if It = nil then
  begin
    ShowMessage('미리볼 알람을 선택하세요.');
    Exit;
  end;
  FireAlarm(It.Title, It.Ment);
end;

{ ---------- 알람 발생 ---------- }

procedure TfrmDash.FireAlarm(const ATitle, AMent: string);
begin
  TfrmAlarm.Popup(ATitle, AMent, FAlarmStack);
  Inc(FAlarmStack);
  if FAlarmStack > 4 then FAlarmStack := 0;   // 화면 넘침 방지
end;

procedure TfrmDash.CheckAlarms;
var
  N: TDateTime;
  Todo: TTodoItem;
  Al: TPcAlarm;
  Ev: TCalEvent;
  Tk: TGoogleTask;
  TA: TTaskAlarm;
begin
  N := Now;

  // 1) 로컬 할일 알람
  for Todo in FTodos do
    if Todo.DueAlarm(N) then
    begin
      Todo.LastAlarm := N;
      FireAlarm('[할일] ' + Todo.Title, Todo.Ment);
      FTodos.SaveToFile(FTodoFile);
      RefreshTodo;
    end;

  // 2) PC 알람 (반복)
  for Al in FAlarms do
    if Al.DueNow(N) then
    begin
      Al.LastFire := N;
      FireAlarm('[알람] ' + Al.Title, Al.Ment);
      FAlarms.SaveToFile(FAlarmFile);
      RefreshAlarm;
    end;

  // 3) 구글 Tasks 알람 (기한 당일, 지정 시각)
  if FGTasks <> nil then
    for Tk in FGTasks do
    begin
      TA := FTaskAlarms.FindById(Tk.Id);
      if (TA <> nil) and TA.DueAlarm(N, Tk.Due, Tk.HasDue) then
      begin
        TA.LastAlarm := N;
        FireAlarm('[할일] ' + Tk.Title, TA.Ment);
        FTaskAlarms.SaveToFile(FTaskAlarmFile);
      end;
    end;

  // 4) 구글 캘린더 일정 알람 (시간이 지정된 항목, 정시)
  if FCalCache <> nil then
    for Ev in FCalCache do
      if Ev.HasTime and SameDate(Ev.StartTime, DateOf(N)) and
         (HourOf(Ev.StartTime) = HourOf(N)) and
         (MinuteOf(Ev.StartTime) = MinuteOf(N)) and
         (SecondOf(N) < 2) then
        FireAlarm('[구글] ' + Ev.Summary, '');
end;

procedure TfrmDash.Timer1Timer(Sender: TObject);
begin
  if FLoading then Exit;

  // 부팅 직후 3초 뒤 한 번 더 중앙으로 끌어올린다 (다른 창에 가려지는 것 방지)
  if FBootTicks > 0 then
  begin
    Inc(FBootTicks);
    if FBootTicks >= 4 then
    begin
      FBootTicks := 0;
      BringUpFront;
    end;
  end;

  CheckAlarms;

  // 날짜가 바뀌면 로컬 백업 + 팔로업 재스캔 (드라이브 백업은 종료 시에 수행)
  if FLastBackup <> Date then
  begin
    DoBackup(False);
    CheckFollowUps;
  end;

  // 자동 갱신 (30분): 캘린더 + 구글 할일
  if chkAutoFetch.Checked and (MinutesBetween(Now, FLastFetch) >= 30) then
  begin
    if Trim(FSet.CalUrl) <> '' then
      btnFetchClick(nil);
    if FGAuth.IsConnected then
      FetchGoogleTasks;
    FLastFetch := Now;
  end;
end;

{ ---------- 스케줄러 열기 ---------- }

procedure TfrmDash.btnSchedulerClick(Sender: TObject);
begin
  if frmMain = nil then
    frmMain := TfrmMain.Create(Application);
  frmMain.Show;
  frmMain.WindowState := wsNormal;
  frmMain.BringToFront;
end;

{ ---------- 트레이 / 종료 ---------- }

{ 종료 시 남아있는 알람 팝업과 타이머를 모두 정리한다 }
procedure TfrmDash.ShutdownAll;
var
  I: Integer;
  F: TForm;
begin
  Timer1.Enabled := False;

  // 종료 시 구글 드라이브 백업 (연결돼 있을 때만, 실패해도 종료는 진행)
  try
    BackupToDrive(False);
  except
  end;

  // 떠 있는 알람 팝업 전부 닫기 (StayOnTop 창이 남아 종료를 막는 것 방지)
  for I := Screen.FormCount - 1 downto 0 do
  begin
    F := Screen.Forms[I];
    if (F <> Self) and (F is TfrmAlarm) then
    begin
      TfrmAlarm(F).StopAlarm;
      F.Close;
    end;
  end;

  // 스케줄러 폼 타이머 정지 후 해제
  if frmMain <> nil then
  begin
    frmMain.StopTimer;
    frmMain.Hide;
  end;

  TrayIcon1.Visible := False;
end;

procedure TfrmDash.FormCloseQuery(Sender: TObject; var CanClose: Boolean);
begin
  if FDuplicate then
  begin
    CanClose := True;   // 중복 인스턴스는 그냥 닫히게 둔다
    Exit;
  end;
  if FReallyClose then
  begin
    CanClose := True;
    Exit;
  end;
  case MessageDlg('창을 닫습니다.' + sLineBreak +
    '[예] 트레이로 최소화 (알람 계속 동작)' + sLineBreak +
    '[아니오] 완전 종료',
    mtConfirmation, [mbYes, mbNo, mbCancel], 0) of
    mrYes:
      begin
        CanClose := False;
        Hide;
        TrayIcon1.BalloonTitle := '일정관리기';
        TrayIcon1.BalloonHint := '트레이에서 계속 실행 중입니다.';
        TrayIcon1.ShowBalloonHint;
      end;
    mrNo:
      begin
        FReallyClose := True;
        ShutdownAll;
        CanClose := True;
        // 남은 창이 있어도 확실히 프로세스를 끝낸다
        Application.Terminate;
      end;
  else
    CanClose := False;
  end;
end;

procedure TfrmDash.TrayIcon1DblClick(Sender: TObject);
begin
  miShowClick(nil);
end;

procedure TfrmDash.miShowClick(Sender: TObject);
begin
  if FDuplicate then Exit;
  Show;
  WindowState := wsNormal;
  Application.BringToFront;
end;

procedure TfrmDash.Notify(const ATitle, AText: string);
begin
  if not TrayIcon1.Visible then Exit;
  TrayIcon1.BalloonTitle := ATitle;
  TrayIcon1.BalloonHint := AText;
  TrayIcon1.ShowBalloonHint;
end;

{ 실행 중인 폼과 트레이 아이콘을 실제로 세어 보여준다 (중복 원인 추적용) }
procedure TfrmDash.miDiagClick(Sender: TObject);
var
  SL: TStringList;
  I, J, TrayCount: Integer;
  F: TForm;
  C: TComponent;
begin
  SL := TStringList.Create;
  try
    SL.Add('실행 파일: ' + ParamStr(0));
    SL.Add('프로세스 ID: ' + IntToStr(GetCurrentProcessId));
    SL.Add('');
    SL.Add('폼 개수: ' + IntToStr(Screen.FormCount));
    TrayCount := 0;
    for I := 0 to Screen.FormCount - 1 do
    begin
      F := Screen.Forms[I];
      SL.Add(Format('  %d) %s (%s)  보임=%s',
        [I + 1, F.Name, F.ClassName, BoolToStr(F.Visible, True)]));
      for J := 0 to F.ComponentCount - 1 do
      begin
        C := F.Components[J];
        if C is TTrayIcon then
        begin
          Inc(TrayCount);
          SL.Add(Format('       └ 트레이: %s  표시=%s',
            [C.Name, BoolToStr(TTrayIcon(C).Visible, True)]));
        end;
      end;
    end;
    SL.Add('');
    SL.Add('트레이 아이콘 총 개수: ' + IntToStr(TrayCount));
    SL.Add('(정상: 폼 2개[frmDash+frmMain] / 트레이 1개)');
    if TrayCount > 1 then
    begin
      SL.Add('');
      SL.Add('※ 트레이가 2개 이상입니다.');
      SL.Add('   프로젝트의 .dpr 파일에서');
      SL.Add('   Application.CreateForm(TfrmDash, frmDash);');
      SL.Add('   줄이 한 번만 있는지 확인하세요.');
    end;
    MessageDlg(SL.Text, mtInformation, [mbOK], 0);
  finally
    SL.Free;
  end;
end;

procedure TfrmDash.miBackupClick(Sender: TObject);
begin
  DoBackup(True);
end;

procedure TfrmDash.miExitClick(Sender: TObject);
begin
  if MessageDlg('프로그램을 종료하면 알람과 예약이 모두 중지됩니다. 종료할까요?',
    mtConfirmation, [mbYes, mbNo], 0) <> mrYes then Exit;
  FReallyClose := True;
  ShutdownAll;
  Close;
  Application.Terminate;
end;

end.
