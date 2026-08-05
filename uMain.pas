unit uMain;

interface

uses
  Winapi.Windows, Winapi.Messages, System.SysUtils, System.Classes,
  System.IOUtils, System.DateUtils, System.StrUtils, System.JSON,
  System.Win.Registry,
  Vcl.Graphics, Vcl.Controls, Vcl.Forms, Vcl.Dialogs, Vcl.StdCtrls,
  Vcl.ExtCtrls, Vcl.ComCtrls, Vcl.Menus,
  uSchedule, uKakaoSend;

type
  // X 버튼을 눌렀을 때 동작
  TCloseAction = (caAsk, caTray, caExit);

  TfrmMain = class(TForm)
    pnlTop: TPanel;
    lblStatus: TLabel;
    btnAdd: TButton;
    btnEdit: TButton;
    btnCopy: TButton;
    btnDel: TButton;
    btnTest: TButton;
    btnDiag: TButton;
    pnlOpt: TPanel;
    lblDelay: TLabel;
    lblPaste: TLabel;
    edDelay: TEdit;
    edPaste: TEdit;
    chkStartup: TCheckBox;
    btnClearLog: TButton;
    mLog: TMemo;
    splLog: TSplitter;
    lvItems: TListView;
    Timer1: TTimer;
    dlgOpen: TOpenDialog;
    procedure FormCreate(Sender: TObject);
    procedure FormDestroy(Sender: TObject);
    procedure FormCloseQuery(Sender: TObject; var CanClose: Boolean);
    procedure Timer1Timer(Sender: TObject);
    procedure btnAddClick(Sender: TObject);
    procedure btnEditClick(Sender: TObject);
    procedure btnCopyClick(Sender: TObject);
    procedure btnDelClick(Sender: TObject);
    procedure btnTestClick(Sender: TObject);
    procedure btnDiagClick(Sender: TObject);
    procedure btnClearLogClick(Sender: TObject);
    procedure chkStartupClick(Sender: TObject);
    procedure lvItemsDblClick(Sender: TObject);
  private
    FItems: TScheduleList;
    FReallyClose: Boolean;
    FDataFile: string;
    FCfgFile: string;
    FLogDir: string;
    FLoading: Boolean;
    FCloseAction: TCloseAction;
    FLastActive: Integer;      // -1 미정 / 0 미실행 / 1 감지됨
    FIconOn: TIcon;
    FIconOff: TIcon;
    // 런타임 생성 컨트롤 (DFM 수정 불필요)
    lblClose: TLabel;
    cbClose: TComboBox;
    btnMin: TButton;
    procedure btnMinClick(Sender: TObject);
    procedure BuildRuntimeControls;
    procedure BuildIcons;
    procedure ApplyCaptions;
    procedure RefreshList;
    procedure Log(const S: string);
    procedure SaveData;
    procedure LoadConfig;
    procedure SaveConfig;
    procedure cbCloseChange(Sender: TObject);
    procedure ExecuteItem(AItem: TScheduleItem; AManual: Boolean);
    function SelectedItem: TScheduleItem;
    procedure SetStartup(AEnable: Boolean);
    function IsStartupSet: Boolean;
    procedure UpdateStatus;
    function DelayMs: Integer;
    function PasteMs: Integer;
    function RoomIsOpen(const ARoom: string): Boolean;
    function AskCloseAction: Integer;   // 1=트레이 2=종료 0=취소
  public
    procedure StopTimer;
  end;

var
  frmMain: TfrmMain;

implementation

{$R *.dfm}

uses uEditItem, uDash;

const
  RUN_KEY   = 'Software\Microsoft\Windows\CurrentVersion\Run';
  RUN_VALUE = 'KakaoScheduler';

{ ---------- 트레이 아이콘 생성 ---------- }

function CreateStateIcon(ABack: TColor; const AMark: string): TIcon;
var
  Bmp, Mask: TBitmap;
  II: TIconInfo;
begin
  Bmp := TBitmap.Create;
  Mask := TBitmap.Create;
  try
    Bmp.PixelFormat := pf32bit;
    Bmp.SetSize(32, 32);
    Bmp.Canvas.Brush.Color := ABack;
    Bmp.Canvas.Brush.Style := bsSolid;
    Bmp.Canvas.Pen.Color := ABack;
    Bmp.Canvas.RoundRect(0, 0, 32, 32, 8, 8);

    // 문자 대신 흰 원 (한글 렌더링 의존 제거)
    Bmp.Canvas.Brush.Color := clWhite;
    Bmp.Canvas.Pen.Color := clWhite;
    Bmp.Canvas.Ellipse(9, 9, 23, 23);

    // 마스크 전체 0(검정) = 전부 불투명
    Mask.Monochrome := True;
    Mask.SetSize(32, 32);
    Mask.Canvas.Brush.Color := clBlack;
    Mask.Canvas.FillRect(Rect(0, 0, 32, 32));

    FillChar(II, SizeOf(II), 0);
    II.fIcon := True;
    II.hbmMask := Mask.Handle;
    II.hbmColor := Bmp.Handle;

    Result := TIcon.Create;
    Result.Handle := CreateIconIndirect(II);
  finally
    Bmp.Free;
    Mask.Free;
  end;
end;

procedure TfrmMain.BuildIcons;
begin
  FIconOn  := CreateStateIcon($00408020, '예');   // 초록 - 카카오톡 감지됨
  FIconOff := CreateStateIcon($00808080, '예');   // 회색 - 카카오톡 미실행
  FLastActive := -1;
end;

{ ---------- 런타임 컨트롤 ---------- }

procedure TfrmMain.BuildRuntimeControls;
begin
  btnMin := TButton.Create(Self);
  btnMin.Parent := pnlTop;
  btnMin.Left := 552;
  btnMin.Top := 12;
  btnMin.Width := 120;
  btnMin.Height := 27;
  btnMin.Caption := '채팅방 창 최소화';
  btnMin.OnClick := btnMinClick;

  lblStatus.Left := 700;

  lblClose := TLabel.Create(Self);
  lblClose.Parent := pnlOpt;
  lblClose.Left := 612;
  lblClose.Top := 17;
  lblClose.Caption := 'X 버튼';

  cbClose := TComboBox.Create(Self);
  cbClose.Parent := pnlOpt;
  cbClose.Left := 665;
  cbClose.Top := 13;
  cbClose.Width := 165;
  cbClose.Style := csDropDownList;
  cbClose.Items.Add('누를 때마다 물어보기');
  cbClose.Items.Add('트레이로 최소화');
  cbClose.Items.Add('프로그램 종료');
  cbClose.ItemIndex := 0;
  cbClose.OnChange := cbCloseChange;
end;

{
  예약에 등록된 채팅방 창들을 한 번에 최소화한다.
  창은 살아 있으므로 발송이 가능하고, 화면에서는 사라져 업무에 방해되지 않는다.
}
procedure TfrmMain.btnMinClick(Sender: TObject);
var
  It: TScheduleItem;
  Done: TStringList;
  OkCnt, MissCnt: Integer;
begin
  Done := TStringList.Create;
  try
    Done.Duplicates := dupIgnore;
    Done.Sorted := True;
    OkCnt := 0;
    MissCnt := 0;
    for It in FItems do
    begin
      if (not It.Enabled) or (Trim(It.RoomName) = '') then Continue;
      if Done.IndexOf(It.RoomName) >= 0 then Continue;
      Done.Add(It.RoomName);
      if TKakaoSender.MinimizeRoom(It.RoomName) then
        Inc(OkCnt)
      else
      begin
        Inc(MissCnt);
        Log(Format('[창정리] 채팅방 [%s] 창이 열려 있지 않습니다', [It.RoomName]));
      end;
    end;
    Log(Format('[창정리] 최소화 %d개 / 미개설 %d개', [OkCnt, MissCnt]));
  finally
    Done.Free;
  end;
end;

procedure TfrmMain.cbCloseChange(Sender: TObject);
begin
  if FLoading then Exit;
  FCloseAction := TCloseAction(cbClose.ItemIndex);
  SaveConfig;
end;

{ ---------- 초기화 ---------- }

procedure TfrmMain.FormCreate(Sender: TObject);
var
  Dir: string;
begin
  FLoading := True;
  FReallyClose := False;

  Dir := TPath.Combine(TPath.GetHomePath, 'KakaoScheduler');
  if not TDirectory.Exists(Dir) then
    TDirectory.CreateDirectory(Dir);
  FDataFile := TPath.Combine(Dir, 'schedules.json');
  FCfgFile := TPath.Combine(Dir, 'config.json');
  FLogDir := TPath.Combine(Dir, 'logs');
  if not TDirectory.Exists(FLogDir) then
    TDirectory.CreateDirectory(FLogDir);

  BuildRuntimeControls;
  BuildIcons;
  ApplyCaptions;


  FItems := TScheduleList.Create(True);
  try
    FItems.LoadFromFile(FDataFile);
  except
    on E: Exception do
      Log('예약 파일을 읽지 못했습니다: ' + E.Message);
  end;

  LoadConfig;
  chkStartup.Checked := IsStartupSet;
  RefreshList;
  UpdateStatus;

  Log(Format('프로그램 시작 (예약 %d건 로드)', [FItems.Count]));
  Log('데이터 폴더: ' + Dir);

  FLoading := False;
end;

procedure TfrmMain.StopTimer;
begin
  Timer1.Enabled := False;
end;

procedure TfrmMain.FormDestroy(Sender: TObject);
begin
  SaveConfig;
  FItems.Free;
  FIconOn.Free;
  FIconOff.Free;
end;

procedure TfrmMain.ApplyCaptions;
begin
  Caption             := '카카오톡 예약 발송기';
  btnAdd.Caption      := '추가';
  btnEdit.Caption     := '수정';
  btnCopy.Caption     := '복제';
  btnDel.Caption      := '삭제';
  btnTest.Caption     := '지금 발송';
  btnDiag.Caption     := '구조 진단';
  btnClearLog.Caption := '로그 지우기';
  lblDelay.Caption    := '전송 간격(ms)';
  lblPaste.Caption    := '이미지 대기(ms)';
  chkStartup.Caption  := 'PC 시작 시 자동 실행';
  chkStartup.Visible  := False;   // 시작 등록은 메인(일정관리기)에서 담당

  lvItems.Columns[0].Caption := '사용';
  lvItems.Columns[1].Caption := '예약 이름';
  lvItems.Columns[2].Caption := '채팅방';
  lvItems.Columns[3].Caption := '시각';
  lvItems.Columns[4].Caption := '반복';
  lvItems.Columns[5].Caption := '형태';
  lvItems.Columns[6].Caption := '마지막 실행';
end;

{ ---------- 설정 저장/로드 ---------- }

procedure TfrmMain.LoadConfig;
var
  V: TJSONValue;
  O: TJSONObject;
begin
  FCloseAction := caAsk;
  if not FileExists(FCfgFile) then
  begin
    cbClose.ItemIndex := 0;
    Exit;
  end;
  V := nil;
  try
    V := TJSONObject.ParseJSONValue(TFile.ReadAllText(FCfgFile, TEncoding.UTF8));
    if V is TJSONObject then
    begin
      O := TJSONObject(V);
      edDelay.Text := O.GetValue<string>('delay', '400');
      edPaste.Text := O.GetValue<string>('paste', '1500');
      FCloseAction := TCloseAction(O.GetValue<Integer>('closeAction', 0));
    end;
  except
    // 설정 파일이 깨졌으면 기본값 사용
  end;
  V.Free;
  cbClose.ItemIndex := Ord(FCloseAction);
end;

procedure TfrmMain.SaveConfig;
var
  O: TJSONObject;
begin
  O := TJSONObject.Create;
  try
    O.AddPair('delay', Trim(edDelay.Text));
    O.AddPair('paste', Trim(edPaste.Text));
    O.AddPair('closeAction', TJSONNumber.Create(Ord(FCloseAction)));
    TFile.WriteAllText(FCfgFile, O.ToJSON, TEncoding.UTF8);
  except
    // 저장 실패는 무시
  end;
  O.Free;
end;

{ ---------- 목록 ---------- }

procedure TfrmMain.RefreshList;
var
  It: TScheduleItem;
  LI: TListItem;
  Idx: Integer;
begin
  Idx := lvItems.ItemIndex;
  lvItems.Items.BeginUpdate;
  try
    lvItems.Items.Clear;
    for It in FItems do
    begin
      LI := lvItems.Items.Add;
      LI.Caption := IfThen(It.Enabled, 'ON', 'OFF');
      LI.SubItems.Add(It.Title);
      LI.SubItems.Add(It.RoomName);
      LI.SubItems.Add(FormatDateTime('hh:nn', It.RunTime));
      LI.SubItems.Add(It.RepeatText);
      LI.SubItems.Add(IfThen(It.UseImage, '텍스트+이미지', '텍스트'));
      if It.LastRun > 0 then
        LI.SubItems.Add(FormatDateTime('yyyy-mm-dd hh:nn', It.LastRun))
      else
        LI.SubItems.Add('-');
      LI.Data := It;
    end;
  finally
    lvItems.Items.EndUpdate;
  end;
  if (Idx >= 0) and (Idx < lvItems.Items.Count) then
    lvItems.ItemIndex := Idx;
end;

function TfrmMain.SelectedItem: TScheduleItem;
begin
  Result := nil;
  if lvItems.Selected <> nil then
    Result := TScheduleItem(lvItems.Selected.Data);
end;

procedure TfrmMain.SaveData;
begin
  try
    FItems.SaveToFile(FDataFile);
  except
    on E: Exception do
      Log('저장 실패: ' + E.Message);
  end;
end;

{ ---------- 로그 ---------- }

procedure TfrmMain.Log(const S: string);
var
  Line, F: string;
begin
  Line := FormatDateTime('yyyy-mm-dd hh:nn:ss', Now) + '  ' + S;
  if Assigned(mLog) then
  begin
    mLog.Lines.Add(Line);
    if mLog.Lines.Count > 2000 then
      while mLog.Lines.Count > 1500 do
        mLog.Lines.Delete(0);
    SendMessage(mLog.Handle, EM_LINESCROLL, 0, mLog.Lines.Count);
  end;

  try
    F := TPath.Combine(FLogDir, FormatDateTime('yyyy-mm-dd', Date) + '.log');
    TFile.AppendAllText(F, Line + sLineBreak, TEncoding.UTF8);
  except
    // 로그 파일 실패는 무시
  end;
end;

procedure TfrmMain.btnClearLogClick(Sender: TObject);
begin
  mLog.Clear;
end;

{ ---------- 설정값 ---------- }

function TfrmMain.DelayMs: Integer;
begin
  Result := StrToIntDef(Trim(edDelay.Text), 400);
  if Result < 100 then Result := 100;
  if Result > 30000 then Result := 30000;
end;

function TfrmMain.PasteMs: Integer;
begin
  Result := StrToIntDef(Trim(edPaste.Text), 1500);
  if Result < 300 then Result := 300;
  if Result > 60000 then Result := 60000;
end;

procedure TfrmMain.UpdateStatus;
var
  Active: Integer;
begin
  if TKakaoSender.IsKakaoRunning then Active := 1 else Active := 0;
  if Active = FLastActive then Exit;
  FLastActive := Active;

  if Active = 1 then
  begin
    lblStatus.Caption := '카카오톡 감지됨';
    lblStatus.Font.Color := clGreen;
  end
  else
  begin
    lblStatus.Caption := '카카오톡 미실행';
    lblStatus.Font.Color := clRed;
  end;
end;

function TfrmMain.RoomIsOpen(const ARoom: string): Boolean;
var
  SL: TStringList;
begin
  SL := TStringList.Create;
  try
    TKakaoSender.ListChatWindows(SL);
    Result := SL.IndexOf(Trim(ARoom)) >= 0;
  finally
    SL.Free;
  end;
end;

{ ---------- 발송 ---------- }

procedure TfrmMain.ExecuteItem(AItem: TScheduleItem; AManual: Boolean);
var
  R: TSendResult;
  Tag: string;
begin
  if AManual then Tag := '[수동] ' else Tag := '[예약] ';

  if AItem.UseImage then
    R := TKakaoSender.SendImage(AItem.RoomName, AItem.MsgText, AItem.ImageFile,
      PasteMs, DelayMs)
  else
    R := TKakaoSender.SendText(AItem.RoomName, AItem.MsgText, DelayMs);

  if R.Success then
  begin
    if R.ErrorMsg <> '' then
      Log(Format('%s%s -> [%s] 발송완료 (방식: %s)',
        [Tag, AItem.Title, AItem.RoomName, R.ErrorMsg]))
    else
      Log(Format('%s%s -> [%s] 발송완료', [Tag, AItem.Title, AItem.RoomName]));
  end
  else
    Log(Format('%s%s -> [%s] 발송실패 : %s',
      [Tag, AItem.Title, AItem.RoomName, R.ErrorMsg]));

  AItem.LastRun := Now;
  SaveData;
  RefreshList;
end;

procedure TfrmMain.Timer1Timer(Sender: TObject);
var
  It: TScheduleItem;
  N: TDateTime;
  Due: TArray<TScheduleItem>;
  I, NowMin, TgtMin: Integer;
begin
  UpdateStatus;
  if FLoading then Exit;

  N := Now;
  SetLength(Due, 0);
  NowMin := HourOf(N) * 60 + MinuteOf(N);

  for It in FItems do
  begin
    if It.DueNow(N) then
    begin
      SetLength(Due, Length(Due) + 1);
      Due[High(Due)] := It;
    end;

    // 발송 1분 전 사전 점검
    if It.Enabled and (SecondOf(N) = 0) then
    begin
      TgtMin := HourOf(It.RunTime) * 60 + MinuteOf(It.RunTime);
      if (TgtMin - NowMin = 1) and (not RoomIsOpen(It.RoomName)) then
      begin
        Log(Format('[사전점검] 1분 뒤 "%s" 발송 예정인데 채팅방 [%s] 창이 닫혀 있습니다',
          [It.Title, It.RoomName]));
        // 트레이 알림은 메인(일정관리기)의 트레이를 통해 띄운다
        if frmDash <> nil then
          frmDash.Notify('채팅방 창을 열어주세요',
            Format('1분 뒤 "%s" 발송 예정 - [%s] 창이 닫혀 있습니다',
              [It.Title, It.RoomName]));
      end;
    end;
  end;

  for I := 0 to High(Due) do
  begin
    ExecuteItem(Due[I], False);
    if I < High(Due) then
      Sleep(DelayMs);
  end;
end;

procedure TfrmMain.btnTestClick(Sender: TObject);
var
  It: TScheduleItem;
begin
  It := SelectedItem;
  if It = nil then
  begin
    ShowMessage('목록에서 예약을 선택하세요.');
    Exit;
  end;
  ExecuteItem(It, True);
end;

procedure TfrmMain.btnDiagClick(Sender: TObject);
var
  It: TScheduleItem;
  Room, S: string;
begin
  It := SelectedItem;
  if It <> nil then Room := It.RoomName else Room := '';
  S := TKakaoSender.Diagnose(Room);
  mLog.Lines.Add('');
  mLog.Lines.Add(S);
  SendMessage(mLog.Handle, EM_LINESCROLL, 0, mLog.Lines.Count);
end;

{ ---------- 예약 편집 ---------- }

procedure TfrmMain.btnAddClick(Sender: TObject);
var
  It: TScheduleItem;
begin
  It := TScheduleItem.Create;
  if TfrmEditItem.Edit(It) then
  begin
    FItems.Add(It);
    SaveData;
    RefreshList;
    Log('예약 추가: ' + It.Title);
  end
  else
    It.Free;
end;

procedure TfrmMain.btnEditClick(Sender: TObject);
var
  It: TScheduleItem;
begin
  It := SelectedItem;
  if It = nil then Exit;
  if TfrmEditItem.Edit(It) then
  begin
    SaveData;
    RefreshList;
    Log('예약 수정: ' + It.Title);
  end;
end;

procedure TfrmMain.lvItemsDblClick(Sender: TObject);
begin
  btnEditClick(nil);
end;

procedure TfrmMain.btnCopyClick(Sender: TObject);
var
  Src, New: TScheduleItem;
begin
  Src := SelectedItem;
  if Src = nil then Exit;
  New := TScheduleItem.Create;
  New.Assign(Src);
  New.Title := Src.Title + ' (복사본)';
  New.LastRun := 0;
  FItems.Add(New);
  SaveData;
  RefreshList;
end;

procedure TfrmMain.btnDelClick(Sender: TObject);
var
  It: TScheduleItem;
begin
  It := SelectedItem;
  if It = nil then Exit;
  if MessageDlg(Format('"%s" 예약을 삭제할까요?', [It.Title]),
    mtConfirmation, [mbYes, mbNo], 0) <> mrYes then Exit;
  Log('예약 삭제: ' + It.Title);
  FItems.Remove(It);
  SaveData;
  RefreshList;
end;

{ ---------- 시작프로그램 등록 ---------- }

function TfrmMain.IsStartupSet: Boolean;
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

procedure TfrmMain.SetStartup(AEnable: Boolean);
var
  Reg: TRegistry;
begin
  Reg := TRegistry.Create(KEY_READ or KEY_WRITE);
  try
    Reg.RootKey := HKEY_CURRENT_USER;
    if Reg.OpenKey(RUN_KEY, True) then
    begin
      if AEnable then
        Reg.WriteString(RUN_VALUE, '"' + ParamStr(0) + '" /tray')
      else if Reg.ValueExists(RUN_VALUE) then
        Reg.DeleteValue(RUN_VALUE);
    end;
  finally
    Reg.Free;
  end;
end;

procedure TfrmMain.chkStartupClick(Sender: TObject);
begin
  if FLoading then Exit;
  try
    SetStartup(chkStartup.Checked);
    if chkStartup.Checked then
      Log('시작프로그램 등록됨')
    else
      Log('시작프로그램 해제됨');
  except
    on E: Exception do
      Log('시작프로그램 설정 실패: ' + E.Message);
  end;
end;

{ ---------- 닫기 동작 ---------- }

function TfrmMain.AskCloseAction: Integer;
var
  TD: TTaskDialog;
  B: TTaskDialogButtonItem;
begin
  Result := 0;
  TD := TTaskDialog.Create(nil);
  try
    try
      TD.Caption := '카카오톡 예약 발송기';
      TD.Title := '창을 닫습니다';
      TD.Text := '어떻게 할까요?';
      TD.CommonButtons := [tcbCancel];
      TD.Flags := [tfUseCommandLinks];
      TD.VerificationText := '다음부터 묻지 않고 이대로 실행';

      B := TD.Buttons.Add as TTaskDialogButtonItem;
      B.Caption := '트레이로 최소화' + sLineBreak + '예약 발송이 계속 동작합니다';
      B.ModalResult := 101;

      B := TD.Buttons.Add as TTaskDialogButtonItem;
      B.Caption := '프로그램 종료' + sLineBreak + '예약 발송이 중지됩니다';
      B.ModalResult := 102;

      if not TD.Execute then Exit(0);

      case TD.ModalResult of
        101: Result := 1;
        102: Result := 2;
      else
        Result := 0;
      end;

      if (Result <> 0) and (tfVerificationFlagChecked in TD.Flags) then
      begin
        if Result = 1 then FCloseAction := caTray else FCloseAction := caExit;
        cbClose.ItemIndex := Ord(FCloseAction);
        SaveConfig;
      end;
    except
      // TaskDialog 를 못 쓰는 환경이면 단순 확인창으로 대체
      case MessageDlg('트레이로 최소화할까요?' + sLineBreak +
        '[예] 트레이 상주   [아니오] 완전 종료',
        mtConfirmation, [mbYes, mbNo, mbCancel], 0) of
        mrYes: Result := 1;
        mrNo:  Result := 2;
      else
        Result := 0;
      end;
    end;
  finally
    TD.Free;
  end;
end;

procedure TfrmMain.FormCloseQuery(Sender: TObject; var CanClose: Boolean);
begin
  if FReallyClose then
  begin
    CanClose := True;
    Exit;
  end;

  // 이 폼은 메인(일정관리기)의 보조 창이므로, 닫으면 종료가 아니라 숨긴다.
  CanClose := False;
  Hide;
end;

end.
