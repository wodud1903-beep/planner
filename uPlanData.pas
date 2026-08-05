unit uPlanData;

{
  일정관리기에서 쓰는 두 가지 데이터.
  - TTodoItem : 로컬 할일 (알람 여부, 시각, 카톡 붙여넣기 멘트)
  - TPcAlarm  : 요일/시간 지정 PC 알람 (최상단 팝업 + 멘트 복사)

  구글 캘린더 이벤트(uCalendar)는 실시간 조회라 여기 저장하지 않는다.
}

interface

uses
  System.SysUtils, System.Classes, System.JSON, System.DateUtils,
  System.IOUtils, System.Generics.Collections;

type
  { 로컬 할일 }
  TTodoItem = class
  public
    Done: Boolean;
    Title: string;
    HasTime: Boolean;
    RunTime: TTime;
    Alarm: Boolean;       // 시각에 팝업 알람
    Ment: string;         // 카톡 붙여넣기용 멘트
    RunDate: TDate;
    Repeats: Boolean;     // True=요일반복 / False=지정일 1회
    WeekDays: string;     // 반복 시 '1'..'7' (1=일 .. 7=토)
    LastAlarm: TDateTime;

    constructor Create;
    procedure Assign(Src: TTodoItem);
    function ToJSON: TJSONObject;
    procedure FromJSON(O: TJSONObject);
    function DueAlarm(ANow: TDateTime): Boolean;
    function DaysText: string;
  end;

  TTodoList = class(TObjectList<TTodoItem>)
  public
    procedure SaveToFile(const AFile: string);
    procedure LoadFromFile(const AFile: string);
  end;

  { PC 알람 (반복) }
  TPcAlarm = class
  public
    Enabled: Boolean;
    Title: string;
    WeekDays: string;     // '1'..'7' (1=일 .. 7=토)
    RunTime: TTime;
    Ment: string;         // 팝업에서 복사할 멘트
    LastFire: TDateTime;

    constructor Create;
    procedure Assign(Src: TPcAlarm);
    function ToJSON: TJSONObject;
    procedure FromJSON(O: TJSONObject);
    function DueNow(ANow: TDateTime): Boolean;
    function DaysText: string;
  end;

  TPcAlarmList = class(TObjectList<TPcAlarm>)
  public
    procedure SaveToFile(const AFile: string);
    procedure LoadFromFile(const AFile: string);
  end;

  { 구글 Tasks 항목에 붙이는 알람 설정 (Tasks 가 원본, 알람만 로컬 보관) }
  TTaskAlarm = class
  public
    GoogleId: string;    // 구글 task id
    Alarm: Boolean;
    RunTime: TTime;      // 기한 당일 몇 시에 알릴지
    Ment: string;        // 카톡 붙여넣기용 멘트
    LastAlarm: TDateTime;

    constructor Create;
    function ToJSON: TJSONObject;
    procedure FromJSON(O: TJSONObject);
    /// ADue = 해당 Task 의 기한일. 기한이 없으면 알람도 없음
    function DueAlarm(ANow: TDateTime; ADue: TDateTime; AHasDue: Boolean): Boolean;
  end;

  TTaskAlarmList = class(TObjectList<TTaskAlarm>)
  public
    function FindById(const AId: string): TTaskAlarm;
    function EnsureById(const AId: string): TTaskAlarm;
    procedure SaveToFile(const AFile: string);
    procedure LoadFromFile(const AFile: string);
  end;

const
  DAY_NAMES: array[1..7] of string = ('일', '월', '화', '수', '목', '금', '토');

implementation

{ ---------- JSON 헬퍼 ---------- }

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

function MakeFS: TFormatSettings;
begin
  Result := TFormatSettings.Invariant;
  Result.DateSeparator := '-';
  Result.ShortDateFormat := 'yyyy-mm-dd';
  Result.TimeSeparator := ':';
  Result.ShortTimeFormat := 'hh:nn';
  Result.LongTimeFormat := 'hh:nn:ss';
end;

{ ---------- TTodoItem ---------- }

constructor TTodoItem.Create;
begin
  inherited;
  Done := False;
  HasTime := True;
  RunTime := EncodeTime(9, 0, 0, 0);
  RunDate := Date;
  Repeats := False;
  WeekDays := '23456';
  Alarm := True;
  LastAlarm := 0;
end;

procedure TTodoItem.Assign(Src: TTodoItem);
begin
  Done := Src.Done; Title := Src.Title; HasTime := Src.HasTime;
  RunTime := Src.RunTime; Alarm := Src.Alarm; Ment := Src.Ment;
  RunDate := Src.RunDate; Repeats := Src.Repeats; WeekDays := Src.WeekDays;
  LastAlarm := Src.LastAlarm;
end;

function TTodoItem.DaysText: string;
var I: Integer;
begin
  if not Repeats then
    Exit(FormatDateTime('mm-dd(ddd)', RunDate));
  Result := '';
  for I := 1 to 7 do
    if Pos(IntToStr(I), WeekDays) > 0 then
      Result := Result + DAY_NAMES[I];
  if Result = '' then Result := '(요일없음)';
end;

function TTodoItem.ToJSON: TJSONObject;
begin
  Result := TJSONObject.Create;
  Result.AddPair('done', TJSONBool.Create(Done));
  Result.AddPair('title', Title);
  Result.AddPair('hasTime', TJSONBool.Create(HasTime));
  Result.AddPair('time', FormatDateTime('hh:nn', RunTime));
  Result.AddPair('alarm', TJSONBool.Create(Alarm));
  Result.AddPair('ment', Ment);
  Result.AddPair('date', FormatDateTime('yyyy-mm-dd', RunDate));
  Result.AddPair('repeats', TJSONBool.Create(Repeats));
  Result.AddPair('weekdays', WeekDays);
  Result.AddPair('lastAlarm', FormatDateTime('yyyy-mm-dd hh:nn:ss', LastAlarm));
end;

procedure TTodoItem.FromJSON(O: TJSONObject);
var
  FS: TFormatSettings;
  T: TDateTime;
begin
  FS := MakeFS;
  Done := JBool(O, 'done', False);
  Title := JStr(O, 'title', '');
  HasTime := JBool(O, 'hasTime', True);
  Alarm := JBool(O, 'alarm', True);
  Ment := JStr(O, 'ment', '');
  Repeats := JBool(O, 'repeats', False);
  WeekDays := JStr(O, 'weekdays', '23456');
  if TryStrToTime(JStr(O, 'time', '09:00'), T, FS) then RunTime := T
  else RunTime := EncodeTime(9, 0, 0, 0);
  if TryStrToDate(JStr(O, 'date', ''), T, FS) then RunDate := T
  else RunDate := Date;
  if TryStrToDateTime(JStr(O, 'lastAlarm', ''), T, FS) then LastAlarm := T
  else LastAlarm := 0;
end;

function TTodoItem.DueAlarm(ANow: TDateTime): Boolean;
var
  NowMin, TgtMin, Dow: Integer;
begin
  Result := False;
  if Done or (not Alarm) or (not HasTime) then Exit;
  NowMin := HourOf(ANow) * 60 + MinuteOf(ANow);
  TgtMin := HourOf(RunTime) * 60 + MinuteOf(RunTime);
  if NowMin <> TgtMin then Exit;
  if (LastAlarm > 0) and (Trunc(LastAlarm * 1440) = Trunc(ANow * 1440)) then Exit;

  if Repeats then
  begin
    Dow := DayOfWeek(ANow);   // 1=일 .. 7=토
    Result := Pos(IntToStr(Dow), WeekDays) > 0;
  end
  else
    Result := SameDate(ANow, RunDate);
end;

{ ---------- TTodoList ---------- }

procedure TTodoList.SaveToFile(const AFile: string);
var
  Arr: TJSONArray;
  It: TTodoItem;
begin
  Arr := TJSONArray.Create;
  try
    for It in Self do Arr.AddElement(It.ToJSON);
    TFile.WriteAllText(AFile, Arr.ToJSON, TEncoding.UTF8);
  finally
    Arr.Free;
  end;
end;

procedure TTodoList.LoadFromFile(const AFile: string);
var
  V: TJSONValue;
  Arr: TJSONArray;
  I: Integer;
  It: TTodoItem;
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
        It := TTodoItem.Create;
        It.FromJSON(TJSONObject(Arr.Items[I]));
        Add(It);
      end;
  finally
    V.Free;
  end;
end;

{ ---------- TPcAlarm ---------- }

constructor TPcAlarm.Create;
begin
  inherited;
  Enabled := True;
  Title := '새 알람';
  WeekDays := '23456';
  RunTime := EncodeTime(9, 0, 0, 0);
  LastFire := 0;
end;

procedure TPcAlarm.Assign(Src: TPcAlarm);
begin
  Enabled := Src.Enabled; Title := Src.Title; WeekDays := Src.WeekDays;
  RunTime := Src.RunTime; Ment := Src.Ment; LastFire := Src.LastFire;
end;

function TPcAlarm.ToJSON: TJSONObject;
begin
  Result := TJSONObject.Create;
  Result.AddPair('enabled', TJSONBool.Create(Enabled));
  Result.AddPair('title', Title);
  Result.AddPair('weekdays', WeekDays);
  Result.AddPair('time', FormatDateTime('hh:nn', RunTime));
  Result.AddPair('ment', Ment);
  Result.AddPair('lastFire', FormatDateTime('yyyy-mm-dd hh:nn:ss', LastFire));
end;

procedure TPcAlarm.FromJSON(O: TJSONObject);
var
  FS: TFormatSettings;
  T: TDateTime;
begin
  FS := MakeFS;
  Enabled := JBool(O, 'enabled', True);
  Title := JStr(O, 'title', '알람');
  WeekDays := JStr(O, 'weekdays', '23456');
  Ment := JStr(O, 'ment', '');
  if TryStrToTime(JStr(O, 'time', '09:00'), T, FS) then RunTime := T
  else RunTime := EncodeTime(9, 0, 0, 0);
  if TryStrToDateTime(JStr(O, 'lastFire', ''), T, FS) then LastFire := T
  else LastFire := 0;
end;

function TPcAlarm.DueNow(ANow: TDateTime): Boolean;
var
  NowMin, TgtMin, Dow: Integer;
begin
  Result := False;
  if not Enabled then Exit;
  NowMin := HourOf(ANow) * 60 + MinuteOf(ANow);
  TgtMin := HourOf(RunTime) * 60 + MinuteOf(RunTime);
  if NowMin <> TgtMin then Exit;
  if (LastFire > 0) and (Trunc(LastFire * 1440) = Trunc(ANow * 1440)) then Exit;
  Dow := DayOfWeek(ANow);   // 1=일 .. 7=토
  Result := Pos(IntToStr(Dow), WeekDays) > 0;
end;

function TPcAlarm.DaysText: string;
var I: Integer;
begin
  Result := '';
  for I := 1 to 7 do
    if Pos(IntToStr(I), WeekDays) > 0 then
      Result := Result + DAY_NAMES[I];
  if Result = '' then Result := '(요일없음)';
end;

{ ---------- TPcAlarmList ---------- }

procedure TPcAlarmList.SaveToFile(const AFile: string);
var
  Arr: TJSONArray;
  It: TPcAlarm;
begin
  Arr := TJSONArray.Create;
  try
    for It in Self do Arr.AddElement(It.ToJSON);
    TFile.WriteAllText(AFile, Arr.ToJSON, TEncoding.UTF8);
  finally
    Arr.Free;
  end;
end;

procedure TPcAlarmList.LoadFromFile(const AFile: string);
var
  V: TJSONValue;
  Arr: TJSONArray;
  I: Integer;
  It: TPcAlarm;
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
        It := TPcAlarm.Create;
        It.FromJSON(TJSONObject(Arr.Items[I]));
        Add(It);
      end;
  finally
    V.Free;
  end;
end;

{ ---------- TTaskAlarm ---------- }

constructor TTaskAlarm.Create;
begin
  inherited;
  Alarm := False;
  RunTime := EncodeTime(9, 0, 0, 0);
  LastAlarm := 0;
end;

function TTaskAlarm.ToJSON: TJSONObject;
begin
  Result := TJSONObject.Create;
  Result.AddPair('id', GoogleId);
  Result.AddPair('alarm', TJSONBool.Create(Alarm));
  Result.AddPair('time', FormatDateTime('hh:nn', RunTime));
  Result.AddPair('ment', Ment);
  Result.AddPair('lastAlarm', FormatDateTime('yyyy-mm-dd hh:nn:ss', LastAlarm));
end;

procedure TTaskAlarm.FromJSON(O: TJSONObject);
var
  FS: TFormatSettings;
  T: TDateTime;
begin
  FS := MakeFS;
  GoogleId := JStr(O, 'id', '');
  Alarm := JBool(O, 'alarm', False);
  Ment := JStr(O, 'ment', '');
  if TryStrToTime(JStr(O, 'time', '09:00'), T, FS) then RunTime := T
  else RunTime := EncodeTime(9, 0, 0, 0);
  if TryStrToDateTime(JStr(O, 'lastAlarm', ''), T, FS) then LastAlarm := T
  else LastAlarm := 0;
end;

function TTaskAlarm.DueAlarm(ANow: TDateTime; ADue: TDateTime; AHasDue: Boolean): Boolean;
var
  NowMin, TgtMin: Integer;
begin
  Result := False;
  if (not Alarm) or (not AHasDue) then Exit;
  if not SameDate(ANow, ADue) then Exit;
  NowMin := HourOf(ANow) * 60 + MinuteOf(ANow);
  TgtMin := HourOf(RunTime) * 60 + MinuteOf(RunTime);
  if NowMin <> TgtMin then Exit;
  if (LastAlarm > 0) and (Trunc(LastAlarm * 1440) = Trunc(ANow * 1440)) then Exit;
  Result := True;
end;

{ ---------- TTaskAlarmList ---------- }

function TTaskAlarmList.FindById(const AId: string): TTaskAlarm;
var
  A: TTaskAlarm;
begin
  Result := nil;
  if AId = '' then Exit;
  for A in Self do
    if A.GoogleId = AId then
      Exit(A);
end;

function TTaskAlarmList.EnsureById(const AId: string): TTaskAlarm;
begin
  Result := FindById(AId);
  if Result = nil then
  begin
    Result := TTaskAlarm.Create;
    Result.GoogleId := AId;
    Add(Result);
  end;
end;

procedure TTaskAlarmList.SaveToFile(const AFile: string);
var
  Arr: TJSONArray;
  It: TTaskAlarm;
begin
  Arr := TJSONArray.Create;
  try
    for It in Self do Arr.AddElement(It.ToJSON);
    TFile.WriteAllText(AFile, Arr.ToJSON, TEncoding.UTF8);
  finally
    Arr.Free;
  end;
end;

procedure TTaskAlarmList.LoadFromFile(const AFile: string);
var
  V: TJSONValue;
  Arr: TJSONArray;
  I: Integer;
  It: TTaskAlarm;
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
        It := TTaskAlarm.Create;
        It.FromJSON(TJSONObject(Arr.Items[I]));
        if It.GoogleId <> '' then Add(It) else It.Free;
      end;
  finally
    V.Free;
  end;
end;

end.