unit uEditItem;

interface

uses
  Winapi.Windows, Winapi.Messages, System.SysUtils, System.Classes,
  System.DateUtils,
  Vcl.Graphics, Vcl.Controls, Vcl.Forms, Vcl.Dialogs, Vcl.StdCtrls,
  Vcl.ExtCtrls, Vcl.ComCtrls,
  uSchedule, uKakaoSend;

type
  TfrmEditItem = class(TForm)
    lblTitle: TLabel;
    lblRoom: TLabel;
    lblText: TLabel;
    lblImage: TLabel;
    lblTime: TLabel;
    lblHint: TLabel;
    edTitle: TEdit;
    cbRoom: TComboBox;
    btnRefreshRooms: TButton;
    mText: TMemo;
    rgType: TRadioGroup;
    edImage: TEdit;
    btnBrowse: TButton;
    rgRepeat: TRadioGroup;
    dtDate: TDateTimePicker;
    dtTime: TDateTimePicker;
    gbDays: TGroupBox;
    chkD1: TCheckBox;
    chkD2: TCheckBox;
    chkD3: TCheckBox;
    chkD4: TCheckBox;
    chkD5: TCheckBox;
    chkD6: TCheckBox;
    chkD7: TCheckBox;
    chkEnabled: TCheckBox;
    btnOK: TButton;
    btnCancel: TButton;
    dlgImage: TOpenDialog;
    procedure FormCreate(Sender: TObject);
    procedure btnRefreshRoomsClick(Sender: TObject);
    procedure btnBrowseClick(Sender: TObject);
    procedure btnOKClick(Sender: TObject);
    procedure rgTypeClick(Sender: TObject);
    procedure rgRepeatClick(Sender: TObject);
  private
    function DayCheck(I: Integer): TCheckBox;
    procedure LoadFrom(AItem: TScheduleItem);
    procedure StoreTo(AItem: TScheduleItem);
    procedure UpdateEnabledStates;
  public
    class function Edit(AItem: TScheduleItem): Boolean;
  end;

implementation

{$R *.dfm}

class function TfrmEditItem.Edit(AItem: TScheduleItem): Boolean;
var
  F: TfrmEditItem;
begin
  F := TfrmEditItem.Create(nil);
  try
    F.LoadFrom(AItem);
    Result := F.ShowModal = mrOk;
    if Result then
      F.StoreTo(AItem);
  finally
    F.Free;
  end;
end;

procedure TfrmEditItem.FormCreate(Sender: TObject);
var
  I: Integer;
begin
  Caption := '예약 편집';
  lblTitle.Caption := '예약 이름';
  lblRoom.Caption  := '채팅방';
  lblText.Caption  := '메시지';
  lblImage.Caption := '이미지';
  lblTime.Caption  := '발송 시각';
  lblHint.Caption  := '※ 채팅방 이름은 카카오톡에서 열려 있는 창 제목과 정확히 같아야 합니다.';

  rgType.Items.Clear;
  rgType.Items.Add('텍스트');
  rgType.Items.Add('텍스트 + 이미지');
  rgType.ItemIndex := 0;

  rgRepeat.Caption := '반복';
  rgRepeat.Items.Clear;
  rgRepeat.Items.Add('지정일 1회');
  rgRepeat.Items.Add('매일');
  rgRepeat.Items.Add('매주');
  rgRepeat.ItemIndex := 1;

  gbDays.Caption := '요일 선택 (매주일 때만)';
  for I := 1 to 7 do
    DayCheck(I).Caption := WEEKDAY_NAMES[I];

  chkEnabled.Caption := '이 예약 사용';
  btnRefreshRooms.Caption := '창 목록';
  btnBrowse.Caption := '찾아보기';
  btnOK.Caption := '확인';
  btnCancel.Caption := '취소';

  btnRefreshRoomsClick(nil);
end;

function TfrmEditItem.DayCheck(I: Integer): TCheckBox;
begin
  case I of
    1: Result := chkD1;
    2: Result := chkD2;
    3: Result := chkD3;
    4: Result := chkD4;
    5: Result := chkD5;
    6: Result := chkD6;
  else
    Result := chkD7;
  end;
end;

procedure TfrmEditItem.btnRefreshRoomsClick(Sender: TObject);
var
  Cur: string;
begin
  Cur := cbRoom.Text;
  TKakaoSender.ListChatWindows(cbRoom.Items);
  cbRoom.Text := Cur;
  if cbRoom.Items.Count = 0 then
    lblHint.Caption := '※ 열려 있는 채팅방 창이 없습니다. 카카오톡에서 채팅방을 먼저 열어주세요.'
  else
    lblHint.Caption := Format('※ 현재 열려 있는 채팅방 %d개를 찾았습니다.', [cbRoom.Items.Count]);
end;

procedure TfrmEditItem.btnBrowseClick(Sender: TObject);
begin
  if dlgImage.Execute then
    edImage.Text := dlgImage.FileName;
end;

procedure TfrmEditItem.rgTypeClick(Sender: TObject);
begin
  UpdateEnabledStates;
end;

procedure TfrmEditItem.rgRepeatClick(Sender: TObject);
begin
  UpdateEnabledStates;
end;

procedure TfrmEditItem.UpdateEnabledStates;
var
  I: Integer;
  UseImg, Weekly, Once: Boolean;
begin
  UseImg := rgType.ItemIndex = 1;
  edImage.Enabled := UseImg;
  btnBrowse.Enabled := UseImg;

  Weekly := rgRepeat.ItemIndex = 2;
  Once := rgRepeat.ItemIndex = 0;

  gbDays.Enabled := Weekly;
  for I := 1 to 7 do
    DayCheck(I).Enabled := Weekly;
  dtDate.Enabled := Once;
end;

procedure TfrmEditItem.LoadFrom(AItem: TScheduleItem);
var
  I: Integer;
begin
  edTitle.Text := AItem.Title;
  cbRoom.Text := AItem.RoomName;
  mText.Lines.Text := AItem.MsgText;
  rgType.ItemIndex := Ord(AItem.UseImage);
  edImage.Text := AItem.ImageFile;
  rgRepeat.ItemIndex := Ord(AItem.RepeatKind);
  if AItem.RunDate > 0 then dtDate.Date := AItem.RunDate;
  dtTime.Time := AItem.RunTime;
  for I := 1 to 7 do
    DayCheck(I).Checked := Pos(IntToStr(I), AItem.WeekDays) > 0;
  chkEnabled.Checked := AItem.Enabled;
  UpdateEnabledStates;
end;

procedure TfrmEditItem.StoreTo(AItem: TScheduleItem);
var
  I: Integer;
  S: string;
begin
  AItem.Title := Trim(edTitle.Text);
  AItem.RoomName := Trim(cbRoom.Text);
  AItem.MsgText := mText.Lines.Text;
  AItem.UseImage := rgType.ItemIndex = 1;
  AItem.ImageFile := Trim(edImage.Text);
  AItem.RepeatKind := TRepeatKind(rgRepeat.ItemIndex);
  AItem.RunDate := dtDate.Date;
  AItem.RunTime := dtTime.Time;
  S := '';
  for I := 1 to 7 do
    if DayCheck(I).Checked then
      S := S + IntToStr(I);
  AItem.WeekDays := S;
  AItem.Enabled := chkEnabled.Checked;
end;

procedure TfrmEditItem.btnOKClick(Sender: TObject);
begin
  if Trim(edTitle.Text) = '' then
  begin
    ShowMessage('예약 이름을 입력하세요.');
    edTitle.SetFocus;
    Exit;
  end;
  if Trim(cbRoom.Text) = '' then
  begin
    ShowMessage('채팅방 이름을 입력하거나 선택하세요.');
    cbRoom.SetFocus;
    Exit;
  end;
  if (rgType.ItemIndex = 1) and (not FileExists(Trim(edImage.Text))) then
  begin
    ShowMessage('이미지 파일을 찾을 수 없습니다.');
    edImage.SetFocus;
    Exit;
  end;
  if (rgType.ItemIndex = 0) and (Trim(mText.Lines.Text) = '') then
  begin
    ShowMessage('보낼 메시지를 입력하세요.');
    mText.SetFocus;
    Exit;
  end;
  if (rgRepeat.ItemIndex = 2) then
  begin
    if (not chkD1.Checked) and (not chkD2.Checked) and (not chkD3.Checked) and
       (not chkD4.Checked) and (not chkD5.Checked) and (not chkD6.Checked) and
       (not chkD7.Checked) then
    begin
      ShowMessage('매주 반복은 요일을 하나 이상 선택해야 합니다.');
      Exit;
    end;
  end;
  ModalResult := mrOk;
end;

end.
