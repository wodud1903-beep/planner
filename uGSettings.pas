unit uGSettings;

{
  통합 설정 창 (탭 3개)
    1) 구글 연동  - 캘린더 ICS 주소 / Tasks OAuth 로그인
    2) 계약 후 팔로업 - 출고 감지 키워드, 개월 수, 알람 시각, 멘트 템플릿
    3) 단축키     - 전역 단축키 ON/OFF 및 조합 변경
}

interface

uses
  Winapi.Windows, Winapi.ShellAPI, System.SysUtils, System.Classes,
  System.IOUtils, Vcl.Graphics, Vcl.Controls, Vcl.Forms, Vcl.Dialogs,
  Vcl.StdCtrls, Vcl.ExtCtrls, Vcl.ComCtrls,
  uGoogleTasks, uPlanData;

type
  TfrmGSettings = class(TForm)
    pgc: TPageControl;
    tsGoogle: TTabSheet;
    gbCal: TGroupBox;
    lblCalUrl: TLabel;
    edCalUrl: TEdit;
    gbTasks: TGroupBox;
    lblStatus: TLabel;
    lblStatusVal: TLabel;
    lblCid: TLabel;
    lblCsec: TLabel;
    edCid: TEdit;
    edCsec: TEdit;
    btnLogin: TButton;
    btnLogout: TButton;
    btnHelp: TButton;
    tsFollow: TTabSheet;
    lblFollowHint: TLabel;
    chkFollowOn: TCheckBox;
    lblKeyword: TLabel;
    edKeyword: TEdit;
    lblMonths: TLabel;
    edMonths: TEdit;
    lblFollowTime: TLabel;
    dtFollowTime: TDateTimePicker;
    chkFollowAlarm: TCheckBox;
    lblFollowMent: TLabel;
    mFollowMent: TMemo;
    tsHotkey: TTabSheet;
    lblHotHint: TLabel;
    chkHotOn: TCheckBox;
    gbCombo: TGroupBox;
    chkCtrl: TCheckBox;
    chkAlt: TCheckBox;
    chkShift: TCheckBox;
    lblKey: TLabel;
    cbKey: TComboBox;
    lblPreview: TLabel;
    btnOK: TButton;
    btnCancel: TButton;
    procedure FormCreate(Sender: TObject);
    procedure btnLoginClick(Sender: TObject);
    procedure btnLogoutClick(Sender: TObject);
    procedure btnHelpClick(Sender: TObject);
    procedure ComboChanged(Sender: TObject);
  private
    FAuth: TGoogleAuth;
    FChanged: Boolean;
    procedure UpdateStatus;
    procedure UpdatePreview;
  public
    class function Edit(AAuth: TGoogleAuth; var ASet: TAppSettings;
      out ATasksChanged: Boolean): Boolean;
  end;

implementation

{$R *.dfm}

procedure TfrmGSettings.FormCreate(Sender: TObject);
var
  C: Char;
  I: Integer;
begin
  Caption := '설정';
  tsGoogle.Caption := '구글 연동';
  tsFollow.Caption := '계약 후 팔로업';
  tsHotkey.Caption := '단축키';

  // --- 구글 탭 ---
  gbCal.Caption := '구글 캘린더 (ICS 구독)';
  lblCalUrl.Caption := 'ICS 주소';
  edCalUrl.TextHint := 'https://calendar.google.com/.../basic.ics';
  gbTasks.Caption := '구글 할일(Tasks) · 드라이브 백업';
  lblStatus.Caption := '연결 상태';
  lblCid.Caption := 'Client ID';
  lblCsec.Caption := 'Client Secret';
  btnLogin.Caption := '구글 로그인';
  btnLogout.Caption := '연결 해제';
  btnHelp.Caption := '설정 도움말';

  // --- 팔로업 탭 ---
  lblFollowHint.Caption :=
    '※ 캘린더의 "고객명 출고" 형식을 찾아, 지정 개월이 되기 3일 전에 [내 할일]에 등록합니다.';
  chkFollowOn.Caption := '팔로업 자동 등록 사용';
  lblKeyword.Caption := '감지 키워드';
  lblMonths.Caption := '개월 뒤';
  lblFollowTime.Caption := '알람 시각';
  chkFollowAlarm.Caption := '알람도 울리기';
  lblFollowMent.Caption := '멘트 템플릿  (%s = 고객명)';

  // --- 단축키 탭 ---
  lblHotHint.Caption :=
    '※ 다른 프로그램 사용 중에도 이 단축키로 일정관리기를 불러옵니다.';
  chkHotOn.Caption := '전역 단축키 사용';
  gbCombo.Caption := '조합 키';
  lblKey.Caption := '키';

  cbKey.Items.Clear;
  for C := 'A' to 'Z' do
    cbKey.Items.Add(C);
  for I := 1 to 12 do
    cbKey.Items.Add('F' + IntToStr(I));
  cbKey.ItemIndex := 0;

  chkHotOn.OnClick := ComboChanged;
  chkCtrl.OnClick := ComboChanged;
  chkAlt.OnClick := ComboChanged;
  chkShift.OnClick := ComboChanged;
  cbKey.OnChange := ComboChanged;

  btnOK.Caption := '확인';
  btnCancel.Caption := '취소';
end;

procedure TfrmGSettings.ComboChanged(Sender: TObject);
begin
  UpdatePreview;
end;

procedure TfrmGSettings.UpdatePreview;
var
  S: string;
begin
  gbCombo.Enabled := chkHotOn.Checked;
  chkCtrl.Enabled := chkHotOn.Checked;
  chkAlt.Enabled := chkHotOn.Checked;
  chkShift.Enabled := chkHotOn.Checked;
  cbKey.Enabled := chkHotOn.Checked;

  if not chkHotOn.Checked then
  begin
    lblPreview.Caption := '단축키 사용 안 함';
    lblPreview.Font.Color := clGrayText;
    Exit;
  end;

  S := '';
  if chkCtrl.Checked then S := S + 'Ctrl + ';
  if chkAlt.Checked then S := S + 'Alt + ';
  if chkShift.Checked then S := S + 'Shift + ';
  if cbKey.ItemIndex >= 0 then S := S + cbKey.Items[cbKey.ItemIndex];

  if (not chkCtrl.Checked) and (not chkAlt.Checked) and (not chkShift.Checked) then
  begin
    lblPreview.Caption := S + '   (조합 키를 최소 1개 선택하세요)';
    lblPreview.Font.Color := clRed;
  end
  else
  begin
    lblPreview.Caption := '현재 단축키:  ' + S;
    lblPreview.Font.Color := clNavy;
  end;
end;

procedure TfrmGSettings.UpdateStatus;
begin
  if FAuth.ClientId = '' then
  begin
    lblStatusVal.Caption := '미설정 (아래 Client ID/Secret 입력)';
    lblStatusVal.Font.Color := clGrayText;
    btnLogin.Enabled := False;
    btnLogout.Enabled := False;
  end
  else if FAuth.IsConnected then
  begin
    lblStatusVal.Caption := '연결됨';
    lblStatusVal.Font.Color := clGreen;
    btnLogin.Enabled := True;
    btnLogout.Enabled := True;
  end
  else
  begin
    lblStatusVal.Caption := '로그인 필요';
    lblStatusVal.Font.Color := clRed;
    btnLogin.Enabled := True;
    btnLogout.Enabled := False;
  end;
end;

procedure TfrmGSettings.btnLoginClick(Sender: TObject);
var
  Err: string;
begin
  FAuth.SetCredentials(Trim(edCid.Text), Trim(edCsec.Text));
  UpdateStatus;
  if FAuth.ClientId = '' then
  begin
    ShowMessage('Client ID / Secret 을 입력하세요.');
    Exit;
  end;

  btnLogin.Enabled := False;
  btnLogin.Caption := '로그인 중...';
  Application.ProcessMessages;
  try
    if FAuth.Authorize(120, Err) then
    begin
      FChanged := True;
      ShowMessage('구글 연결 완료.');
    end
    else
      ShowMessage('구글 로그인 실패:' + sLineBreak + Err);
  finally
    btnLogin.Caption := '구글 로그인';
    UpdateStatus;
  end;
end;

procedure TfrmGSettings.btnLogoutClick(Sender: TObject);
begin
  if MessageDlg('구글 연결을 해제할까요?', mtConfirmation, [mbYes, mbNo], 0) <> mrYes then
    Exit;
  FAuth.Disconnect;
  FChanged := True;
  UpdateStatus;
end;

procedure TfrmGSettings.btnHelpClick(Sender: TObject);
var
  P: string;
begin
  P := TPath.Combine(ExtractFilePath(ParamStr(0)), 'README_GoogleTasks.md');
  if FileExists(P) then
    ShellExecute(0, 'open', PChar(P), nil, nil, SW_SHOWNORMAL)
  else
    ShowMessage('설정 안내 파일(README_GoogleTasks.md)을 실행 파일과 같은 폴더에 두세요.');
end;

class function TfrmGSettings.Edit(AAuth: TGoogleAuth; var ASet: TAppSettings;
  out ATasksChanged: Boolean): Boolean;
var
  F: TfrmGSettings;
  Idx: Integer;
begin
  F := TfrmGSettings.Create(nil);
  try
    F.FAuth := AAuth;
    F.FChanged := False;

    // 구글 탭
    F.edCalUrl.Text := ASet.CalUrl;
    F.edCid.Text := AAuth.ClientId;
    F.edCsec.Text := AAuth.ClientSecret;
    F.UpdateStatus;

    // 팔로업 탭
    F.chkFollowOn.Checked := ASet.FollowOn;
    F.edKeyword.Text := ASet.FollowKeyword;
    F.edMonths.Text := IntToStr(ASet.FollowMonths);
    F.dtFollowTime.Time := ASet.FollowTime;
    F.chkFollowAlarm.Checked := ASet.FollowAlarm;
    F.mFollowMent.Lines.Text := ASet.FollowMent;

    // 단축키 탭
    F.chkHotOn.Checked := ASet.HotOn;
    F.chkCtrl.Checked := ASet.HotCtrl;
    F.chkAlt.Checked := ASet.HotAlt;
    F.chkShift.Checked := ASet.HotShift;
    Idx := F.cbKey.Items.IndexOf(ASet.HotKeyName);
    if Idx < 0 then Idx := 0;
    F.cbKey.ItemIndex := Idx;
    F.UpdatePreview;

    Result := F.ShowModal = mrOk;
    ATasksChanged := F.FChanged;

    if Result then
    begin
      ASet.CalUrl := Trim(F.edCalUrl.Text);
      AAuth.SetCredentials(Trim(F.edCid.Text), Trim(F.edCsec.Text));

      ASet.FollowOn := F.chkFollowOn.Checked;
      ASet.FollowKeyword := Trim(F.edKeyword.Text);
      if ASet.FollowKeyword = '' then ASet.FollowKeyword := '출고';
      ASet.FollowMonths := StrToIntDef(Trim(F.edMonths.Text), 1);
      if ASet.FollowMonths < 0 then ASet.FollowMonths := 0;
      if ASet.FollowMonths > 60 then ASet.FollowMonths := 60;
      ASet.FollowTime := F.dtFollowTime.Time;
      ASet.FollowAlarm := F.chkFollowAlarm.Checked;
      ASet.FollowMent := F.mFollowMent.Lines.Text;

      ASet.HotOn := F.chkHotOn.Checked;
      ASet.HotCtrl := F.chkCtrl.Checked;
      ASet.HotAlt := F.chkAlt.Checked;
      ASet.HotShift := F.chkShift.Checked;
      if F.cbKey.ItemIndex >= 0 then
        ASet.HotKeyName := F.cbKey.Items[F.cbKey.ItemIndex];
      // 조합 키가 하나도 없으면 단축키를 끈다 (등록 실패 방지)
      if ASet.HotOn and (not ASet.HotCtrl) and (not ASet.HotAlt) and (not ASet.HotShift) then
        ASet.HotOn := False;
    end;
  finally
    F.Free;
  end;
end;

end.
