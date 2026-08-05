unit uSchedule;

{
  예약 항목 데이터 모델 + JSON 직렬화.
  schedules.json 파일에 여러 건을 저장한다.
}

interface

uses
  System.SysUtils, System.Classes, System.JSON, System.DateUtils,
  System.Generics.Collections, System.IOUtils;

type
  TRepeatKind = (rkOnce, rkDaily, rkWeekly);

  TScheduleItem = class
  public
    Enabled: Boolean;
    Title: string;         // 예약 이름
    RoomName: string;      // 채팅방 창 제목 (정확히 일치해야 함)
    MsgText: string;       // 보낼 텍스트
    UseImage: Boolean;     // False = 텍스트만 / True = 텍스트+이미지
    ImageFile: string;
    RepeatKind: TRepeatKind;
    RunDate: TDate;        // rkOnce 일 때만 사용
    RunTime: TTime;        // 시:분
    WeekDays: string;      // rkWeekly - '1234567' 중 포함된 요일 (1=일 .. 7=토)
    LastRun: TDateTime;

    constructor Create;
    procedure Assign(Src: TScheduleItem);
    function ToJSON: TJSONObject;
    procedure FromJSON(O: TJSONObject);
    function DueNow(ANow: TDateTime): Boolean;
    function RepeatText: string;
  end;

  TScheduleList = class(TObjectList<TScheduleItem>)
  public
    procedure SaveToFile(const AFile: string);
    procedure LoadFromFile(const AFile: string);
  end;

const
  WEEKDAY_NAMES: array[1..7] of string = ('일', '월', '화', '수', '목', '금', '토');

implementation

{ TScheduleItem }

constructor TScheduleItem.Create;
begin
  inherited Create;
  Enabled := True;
  Title := '새 예약';
  RepeatKind := rkDaily;
  RunDate := Date;
  RunTime := EncodeTime(9, 0, 0, 0);
  WeekDays := '23456';   // 기본 평일
  LastRun := 0;
  UseImage := False;
end;

procedure TScheduleItem.Assign(Src: TScheduleItem);
begin
  Enabled    := Src.Enabled;
  Title      := Src.Title;
  RoomName   := Src.RoomName;
  MsgText    := Src.MsgText;
  UseImage   := Src.UseImage;
  ImageFile  := Src.ImageFile;
  RepeatKind := Src.RepeatKind;
  RunDate    := Src.RunDate;
  RunTime    := Src.RunTime;
  WeekDays   := Src.WeekDays;
  LastRun    := Src.LastRun;
end;

function TScheduleItem.ToJSON: TJSONObject;
begin
  Result := TJSONObject.Create;
  Result.AddPair('enabled', TJSONBool.Create(Enabled));
  Result.AddPair('title', Title);
  Result.AddPair('room', RoomName);
  Result.AddPair('text', MsgText);
  Result.AddPair('useImage', TJSONBool.Create(UseImage));
  Result.AddPair('image', ImageFile);
  Result.AddPair('repeat', TJSONNumber.Create(Ord(RepeatKind)));
  Result.AddPair('date', FormatDateTime('yyyy-mm-dd', RunDate));
  Result.AddPair('time', FormatDateTime('hh:nn', RunTime));
  Result.AddPair('weekdays', WeekDays);
  Result.AddPair('lastRun', FormatDateTime('yyyy-mm-dd hh:nn:ss', LastRun));
end;

function JStr(O: TJSONObject; const K, Def: string): string;
var V: TJSONValue;
begin
  V := O.GetValue(K);
  if (V = nil) or (V is TJSONNull) then Result := Def else Result := V.Value;
end;

function JBool(O: TJSONObject; const K: string; Def: Boolean): Boolean;
var V: TJSONValue;
begin
  V := O.GetValue(K);
  if V is TJSONBool then Result := TJSONBool(V).AsBoolean else Result := Def;
end;

function JInt(O: TJSONObject; const K: string; Def: Integer): Integer;
var V: TJSONValue;
begin
  V := O.GetValue(K);
  if V is TJSONNumber then Result := TJSONNumber(V).AsInt else Result := Def;
end;

procedure TScheduleItem.FromJSON(O: TJSONObject);
var
  FS: TFormatSettings;
  S: string;
  TmpDT: TDateTime;
begin
  FS := TFormatSettings.Invariant;
  FS.DateSeparator := '-';
  FS.ShortDateFormat := 'yyyy-mm-dd';
  FS.TimeSeparator := ':';
  FS.ShortTimeFormat := 'hh:nn';
  FS.LongTimeFormat := 'hh:nn:ss';

  Enabled   := JBool(O, 'enabled', True);
  Title     := JStr(O, 'title', '예약');
  RoomName  := JStr(O, 'room', '');
  MsgText   := JStr(O, 'text', '');
  UseImage  := JBool(O, 'useImage', False);
  ImageFile := JStr(O, 'image', '');
  RepeatKind := TRepeatKind(JInt(O, 'repeat', Ord(rkDaily)));
  WeekDays  := JStr(O, 'weekdays', '23456');

  // TDate / TTime 은 var 파라미터로 직접 넘길 수 없으므로 TDateTime 을 경유한다
  S := JStr(O, 'date', '');
  if TryStrToDate(S, TmpDT, FS) then
    RunDate := TmpDT
  else
    RunDate := Date;

  S := JStr(O, 'time', '09:00');
  if TryStrToTime(S, TmpDT, FS) then
    RunTime := TmpDT
  else
    RunTime := EncodeTime(9, 0, 0, 0);

  S := JStr(O, 'lastRun', '');
  if TryStrToDateTime(S, TmpDT, FS) then
    LastRun := TmpDT
  else
    LastRun := 0;
end;

function TScheduleItem.DueNow(ANow: TDateTime): Boolean;
var
  NowMin, TgtMin, Dow: Integer;
begin
  Result := False;
  if not Enabled then Exit;
  if Trim(RoomName) = '' then Exit;

  NowMin := HourOf(ANow) * 60 + MinuteOf(ANow);
  TgtMin := HourOf(RunTime) * 60 + MinuteOf(RunTime);
  if NowMin <> TgtMin then Exit;

  // 같은 '분' 안에서 중복 실행 방지
  if (LastRun > 0) and (Trunc(LastRun * 1440) = Trunc(ANow * 1440)) then Exit;

  Dow := DayOfWeek(ANow);   // 1=일요일 .. 7=토요일

  case RepeatKind of
    rkOnce:   Result := SameDate(ANow, RunDate);
    rkDaily:  Result := True;
    rkWeekly: Result := Pos(IntToStr(Dow), WeekDays) > 0;
  end;
end;

function TScheduleItem.RepeatText: string;
var
  I: Integer;
  S: string;
begin
  case RepeatKind of
    rkOnce: Result := FormatDateTime('yyyy-mm-dd', RunDate) + ' 1회';
    rkDaily: Result := '매일';
    rkWeekly:
      begin
        S := '';
        for I := 1 to 7 do
          if Pos(IntToStr(I), WeekDays) > 0 then
            S := S + WEEKDAY_NAMES[I];
        if S = '' then S := '(요일 미지정)';
        Result := '매주 ' + S;
      end;
  else
    Result := '';
  end;
end;

{ TScheduleList }

procedure TScheduleList.SaveToFile(const AFile: string);
var
  Arr: TJSONArray;
  It: TScheduleItem;
begin
  Arr := TJSONArray.Create;
  try
    for It in Self do
      Arr.AddElement(It.ToJSON);
    TFile.WriteAllText(AFile, Arr.ToJSON, TEncoding.UTF8);
  finally
    Arr.Free;
  end;
end;

procedure TScheduleList.LoadFromFile(const AFile: string);
var
  V: TJSONValue;
  Arr: TJSONArray;
  I: Integer;
  It: TScheduleItem;
begin
  Clear;
  if not FileExists(AFile) then Exit;

  V := TJSONObject.ParseJSONValue(TFile.ReadAllText(AFile, TEncoding.UTF8));
  if V = nil then Exit;
  try
    if not (V is TJSONArray) then Exit;
    Arr := TJSONArray(V);
    for I := 0 to Arr.Count - 1 do
      if Arr.Items[I] is TJSONObject then
      begin
        It := TScheduleItem.Create;
        It.FromJSON(TJSONObject(Arr.Items[I]));
        Add(It);
      end;
  finally
    V.Free;
  end;
end;

end.
