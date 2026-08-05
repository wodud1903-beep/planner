unit uGSettings;

{
  구글 연동 설정 창.
  - 구글 캘린더 ICS 주소
  - 구글 Tasks OAuth (Client ID/Secret, 로그인/로그아웃)
  메인 화면에서 [설정] 버튼으로 연다.
}

interface

uses
  Winapi.Windows, Winapi.ShellAPI, System.SysUtils, System.Classes,
  System.IOUtils, Vcl.Graphics, Vcl.Controls, Vcl.Forms, Vcl.Dialogs,
  Vcl.StdCtrls, Vcl.ExtCtrls,
  uGoogleTasks;

type
  TfrmGSettings = class(TForm)
    gbCal: TGroupBox;
    lblCalUrl: TLabel;
    edCalUrl: TEdit;
    gbTasks: TGroupBox;
    lblStatus: TLabel;
    lblStatusVal: TLabel;
    lblCid: TLabel;
    edCid: TEdit;
    lblCsec: TLabel;
    edCsec: TEdit;
    btnLogin: TButton;
    btnLogout: TButton;
    btnHelp: TButton;
    btnOK: TButton;
    btnCancel: TButton;
    procedure FormCreate(Sender: TObject);
    procedure btnLoginClick(Sender: TObject);
    procedure btnLogoutClick(Sender: TObject);
    procedure btnHelpClick(Sender: TObject);
  private
    FAuth: TGoogleAuth;
    FChanged: Boolean;   // 로그인/로그아웃/Tasks 변경이 있었는지
    procedure UpdateStatus;
  public
    // 반환: 사용자가 OK. AUrl 은 ICS 주소, AChanged 는 Tasks 상태 변경 여부
    class function Edit(AAuth: TGoogleAuth; var AUrl: string;
      out ATasksChanged: Boolean): Boolean;
  end;

implementation

{$R *.dfm}

procedure TfrmGSettings.FormCreate(Sender: TObject);
begin
  Caption := '연동 설정';
  gbCal.Caption := '구글 캘린더 (ICS 구독)';
  lblCalUrl.Caption := 'ICS 주소';
  edCalUrl.TextHint := 'https://calendar.google.com/.../basic.ics';
  gbTasks.Caption := '구글 할일 (Tasks)';
  lblStatus.Caption := '연결 상태';
  lblCid.Caption := 'Client ID';
  lblCsec.Caption := 'Client Secret';
  btnLogin.Caption := '구글 로그인';
  btnLogout.Caption := '연결 해제';
  btnHelp.Caption := '설정 도움말';
  btnOK.Caption := '확인';
  btnCancel.Caption := '취소';
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
  // 입력한 Client ID/Secret 을 먼저 저장
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

class function TfrmGSettings.Edit(AAuth: TGoogleAuth; var AUrl: string;
  out ATasksChanged: Boolean): Boolean;
var
  F: TfrmGSettings;
begin
  F := TfrmGSettings.Create(nil);
  try
    F.FAuth := AAuth;
    F.FChanged := False;
    F.edCalUrl.Text := AUrl;
    F.edCid.Text := AAuth.ClientId;
    F.edCsec.Text := AAuth.ClientSecret;
    F.UpdateStatus;

    Result := F.ShowModal = mrOk;
    ATasksChanged := F.FChanged;
    if Result then
    begin
      AUrl := Trim(F.edCalUrl.Text);
      // Client ID/Secret 변경도 저장
      AAuth.SetCredentials(Trim(F.edCid.Text), Trim(F.edCsec.Text));
    end;
  finally
    F.Free;
  end;
end;

end.
