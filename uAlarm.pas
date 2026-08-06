unit uAlarm;

{
  화면 최상단 중앙에 뜨는 알람 팝업.
  - 항상 위(fsStayOnTop) + 포커스를 뺏지 않고 표시
  - 멘트가 있으면 [멘트 복사] 버튼으로 클립보드에 복사
  - 여러 개가 동시에 뜨면 아래로 쌓인다 (StackIndex)
}

interface

uses
  Winapi.Windows, Winapi.Messages, System.SysUtils, System.Classes,
  Vcl.Graphics, Vcl.Controls, Vcl.Forms, Vcl.StdCtrls, Vcl.ExtCtrls,
  Vcl.Clipbrd;

type
  TfrmAlarm = class(TForm)
    pnlBar: TPanel;
    lblHead: TLabel;
    btnClose: TButton;
    lblTitle: TLabel;
    mMent: TMemo;
    btnCopy: TButton;
    btnSnooze: TButton;
    btnDismiss: TButton;
    Timer1: TTimer;
    TimerSnooze: TTimer;
    procedure FormCreate(Sender: TObject);
    procedure btnCloseClick(Sender: TObject);
    procedure btnCopyClick(Sender: TObject);
    procedure btnSnoozeClick(Sender: TObject);
    procedure btnDismissClick(Sender: TObject);
    procedure TimerSnoozeTimer(Sender: TObject);
    procedure Timer1Timer(Sender: TObject);
  private
    FBlink: Integer;
    FStackIndex: Integer;
    FSnoozeLeft: Integer;   // 남은 스누즈 초
    FSiren: Boolean;        // False = 조용한 안내 팝업(브리핑 등)
  protected
    procedure CreateParams(var Params: TCreateParams); override;
  public
    procedure StopAlarm;
    class procedure Popup(const ATitle, AMent: string; AStackIndex: Integer;
      ASiren: Boolean = True);
  end;

implementation

{$R *.dfm}

var
  GActiveCount: Integer = 0;

{ 포커스를 뺏지 않는 최상위 창으로 만든다 }
procedure TfrmAlarm.CreateParams(var Params: TCreateParams);
begin
  inherited;
  Params.WndParent := GetDesktopWindow;
  Params.ExStyle := Params.ExStyle or WS_EX_TOPMOST or WS_EX_NOACTIVATE
    or WS_EX_TOOLWINDOW;
end;

procedure TfrmAlarm.FormCreate(Sender: TObject);
begin
  btnCopy.Caption := '멘트 복사';
  btnSnooze.Caption := '5분 뒤 다시';
  btnDismiss.Caption := '확인';
  lblHead.Caption := '일정 알람';
  FBlink := 0;
end;

class procedure TfrmAlarm.Popup(const ATitle, AMent: string; AStackIndex: Integer;
  ASiren: Boolean);
var
  F: TfrmAlarm;
  ScreenW: Integer;
begin
  F := TfrmAlarm.Create(Application);
  F.FStackIndex := AStackIndex;
  F.lblTitle.Caption := ATitle;

  F.FSiren := ASiren;
  F.Timer1.Enabled := ASiren;      // 조용한 안내면 깜빡임/소리 없음
  if not ASiren then
  begin
    F.pnlBar.Color := $001F1F1F;
    F.btnSnooze.Visible := False;
  end;

  if Trim(AMent) = '' then
  begin
    F.mMent.Visible := False;
    F.btnCopy.Visible := False;
    F.ClientHeight := 150;
    F.btnSnooze.Top := 100;
    F.btnSnooze.Left := 18;
    F.btnSnooze.Width := 284;
    F.btnDismiss.Top := 100;
    F.btnDismiss.Left := 318;
    F.btnDismiss.Width := 284;
    if not ASiren then
    begin
      F.btnDismiss.Left := 18;
      F.btnDismiss.Width := 584;
    end;
  end
  else
    F.mMent.Lines.Text := AMent;

  // 화면 상단 중앙, 여러 개면 아래로 쌓기
  ScreenW := Screen.WorkAreaWidth;
  F.Left := Screen.WorkAreaLeft + (ScreenW - F.Width) div 2;
  F.Top := Screen.WorkAreaTop + 20 + AStackIndex * (F.Height + 10);

  Inc(GActiveCount);
  // 포커스 없이 표시
  ShowWindow(F.Handle, SW_SHOWNOACTIVATE);
  F.Visible := True;
  SetWindowPos(F.Handle, HWND_TOPMOST, F.Left, F.Top, 0, 0,
    SWP_NOACTIVATE or SWP_NOSIZE);
  if ASiren then
    MessageBeep(MB_ICONINFORMATION);
end;

procedure TfrmAlarm.Timer1Timer(Sender: TObject);
begin
  // 확인(닫기) 전까지 계속 깜빡이고, 3회마다 소리를 낸다 (사이렌 효과)
  Inc(FBlink);
  if Odd(FBlink) then
  begin
    pnlBar.Color := $003C3CE0;        // 빨강 (BGR)
    Self.Color := $003C3CE0;
    lblTitle.Font.Color := clWhite;
  end
  else
  begin
    pnlBar.Color := $001F1F1F;        // 어두운 회색
    Self.Color := $00353535;
    lblTitle.Font.Color := $0060FFFF; // 노랑
  end;

  // 항상 맨 위로 끌어올린다 (다른 창에 가려지지 않게)
  SetWindowPos(Handle, HWND_TOPMOST, 0, 0, 0, 0,
    SWP_NOACTIVATE or SWP_NOMOVE or SWP_NOSIZE);

  if (FBlink mod 3) = 0 then
    MessageBeep(MB_ICONEXCLAMATION);
end;

procedure TfrmAlarm.btnCopyClick(Sender: TObject);
begin
  try
    Clipboard.AsText := mMent.Lines.Text;
    btnCopy.Caption := '복사됨 ✔';
  except
    btnCopy.Caption := '복사 실패';
  end;
end;

procedure TfrmAlarm.btnSnoozeClick(Sender: TObject);
begin
  // 5분 동안 숨겼다가 다시 울린다
  Timer1.Enabled := False;
  FSnoozeLeft := 5 * 60;
  TimerSnooze.Enabled := True;
  Hide;
end;

procedure TfrmAlarm.TimerSnoozeTimer(Sender: TObject);
begin
  Dec(FSnoozeLeft);
  if FSnoozeLeft > 0 then Exit;

  TimerSnooze.Enabled := False;
  FBlink := 0;
  Timer1.Enabled := FSiren;
  ShowWindow(Handle, SW_SHOWNOACTIVATE);
  Visible := True;
  SetWindowPos(Handle, HWND_TOPMOST, 0, 0, 0, 0,
    SWP_NOACTIVATE or SWP_NOMOVE or SWP_NOSIZE);
  if FSiren then
    MessageBeep(MB_ICONEXCLAMATION);
end;

procedure TfrmAlarm.StopAlarm;
begin
  Timer1.Enabled := False;
  TimerSnooze.Enabled := False;
end;

procedure TfrmAlarm.btnDismissClick(Sender: TObject);
begin
  StopAlarm;
  Close;
end;

procedure TfrmAlarm.btnCloseClick(Sender: TObject);
begin
  StopAlarm;
  Close;
end;

end.
