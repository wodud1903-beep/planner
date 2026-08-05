unit uCalendar;

{
  구글 캘린더 "비공개 ICS 주소"를 다운로드해서 파싱한다.
  - 로그인/OAuth 불필요. ICS URL 하나만 있으면 된다.
  - 날짜가 지정된 구글 '할일'은 캘린더에 표시되어 ICS 피드에 포함된다.

  구글 캘린더 -> 설정 -> (해당 캘린더) -> "비공개 주소(iCal 형식)" URL 복사
}

interface

uses
  Winapi.Windows, System.SysUtils, System.Classes, System.DateUtils,
  System.StrUtils, System.Net.HttpClient, System.Net.URLClient,
  System.Generics.Collections, System.Generics.Defaults;

type
  TCalEvent = class
  public
    UID: string;
    Summary: string;
    StartTime: TDateTime;
    HasTime: Boolean;      // False = 하루 종일(시간 없음)
    IsTodo: Boolean;       // VTODO 항목(구글 할일)
    function TimeText: string;
    function DisplayText: string;
  end;

  TCalEventList = class(TObjectList<TCalEvent>)
  public
    procedure SortByStart;
  end;

  TCalendarFetcher = class
  private
    class function Unfold(const ARaw: string): TStringList;
    class function DecodeText(const S: string): string;
    class function ParseICSDate(V: string; out AHasTime: Boolean): TDateTime;
  public
    /// URL(webcal:// 도 허용)에서 ICS 를 받아 이벤트 목록 반환
    class function Fetch(const AUrl: string; out AError: string): TCalEventList;

    /// 이미 받은 ICS 텍스트를 파싱
    class function ParseICS(const AText: string): TCalEventList;

    /// 목록에서 [AFrom, ATo) 구간의 이벤트만 새 리스트로 반환
    class function FilterRange(ASrc: TCalEventList;
      AFrom, ATo: TDateTime): TCalEventList;
  end;

implementation

{ TCalEvent }

function TCalEvent.TimeText: string;
begin
  if not HasTime then
    Result := '하루종일'
  else
    Result := FormatDateTime('hh:nn', StartTime);
end;

function TCalEvent.DisplayText: string;
begin
  Result := Format('%s  %s%s',
    [TimeText, Summary, IfThen(IsTodo, '  (할일)', '')]);
end;

{ TCalEventList }

procedure TCalEventList.SortByStart;
begin
  Sort(TComparer<TCalEvent>.Construct(
    function(const A, B: TCalEvent): Integer
    begin
      Result := CompareDateTime(A.StartTime, B.StartTime);
    end));
end;

{ TCalendarFetcher }

class function TCalendarFetcher.Unfold(const ARaw: string): TStringList;
var
  Lines: TStringList;
  I: Integer;
  Cur: string;
begin
  Result := TStringList.Create;
  Lines := TStringList.Create;
  try
    Lines.Text := StringReplace(ARaw, #13#10, #10, [rfReplaceAll]);
    Cur := '';
    for I := 0 to Lines.Count - 1 do
    begin
      // ICS 폴딩: 다음 줄이 공백/탭으로 시작하면 앞줄에 이어붙인다
      if (Length(Lines[I]) > 0) and ((Lines[I][1] = ' ') or (Lines[I][1] = #9)) then
        Cur := Cur + Copy(Lines[I], 2, MaxInt)
      else
      begin
        if Cur <> '' then Result.Add(Cur);
        Cur := Lines[I];
      end;
    end;
    if Cur <> '' then Result.Add(Cur);
  finally
    Lines.Free;
  end;
end;

class function TCalendarFetcher.DecodeText(const S: string): string;
begin
  Result := S;
  Result := StringReplace(Result, '\n', sLineBreak, [rfReplaceAll]);
  Result := StringReplace(Result, '\,', ',', [rfReplaceAll]);
  Result := StringReplace(Result, '\;', ';', [rfReplaceAll]);
  Result := StringReplace(Result, '\\', '\', [rfReplaceAll]);
end;

class function TCalendarFetcher.ParseICSDate(V: string; out AHasTime: Boolean): TDateTime;
var
  Y, Mo, D, H, Mi, Se: Word;
  IsUTC: Boolean;
begin
  AHasTime := False;
  Result := 0;
  // 파라미터 제거 (예: DTSTART;TZID=...:20260804T090000)
  if Pos(':', V) > 0 then
    V := Copy(V, Pos(':', V) + 1, MaxInt);
  V := Trim(V);
  if V = '' then Exit;

  IsUTC := (V[Length(V)] = 'Z');
  if IsUTC then SetLength(V, Length(V) - 1);

  if Length(V) < 8 then Exit;
  Y := StrToIntDef(Copy(V, 1, 4), 0);
  Mo := StrToIntDef(Copy(V, 5, 2), 0);
  D := StrToIntDef(Copy(V, 7, 2), 0);
  if (Y = 0) or (Mo = 0) or (D = 0) then Exit;

  if (Length(V) >= 15) and (V[9] = 'T') then
  begin
    AHasTime := True;
    H := StrToIntDef(Copy(V, 10, 2), 0);
    Mi := StrToIntDef(Copy(V, 12, 2), 0);
    Se := StrToIntDef(Copy(V, 14, 2), 0);
    Result := EncodeDateTime(Y, Mo, D, H, Mi, Se, 0);
    // UTC 표기면 로컬(KST=+9)로 변환
    if IsUTC then
      Result := TTimeZone.Local.ToLocalTime(Result);
  end
  else
    Result := EncodeDate(Y, Mo, D);
end;

class function TCalendarFetcher.ParseICS(const AText: string): TCalEventList;
var
  Lines: TStringList;
  I, P: Integer;
  Line, Key, Val: string;
  Ev: TCalEvent;
  InEvent: Boolean;
  Kind: string;   // VEVENT / VTODO
begin
  Result := TCalEventList.Create(True);
  Lines := Unfold(AText);
  try
    Ev := nil;
    InEvent := False;
    Kind := '';
    for I := 0 to Lines.Count - 1 do
    begin
      Line := Lines[I];

      if (Line = 'BEGIN:VEVENT') or (Line = 'BEGIN:VTODO') then
      begin
        InEvent := True;
        if Line = 'BEGIN:VTODO' then Kind := 'VTODO' else Kind := 'VEVENT';
        Ev := TCalEvent.Create;
        Ev.IsTodo := (Kind = 'VTODO');
        Ev.HasTime := False;
        Continue;
      end;

      if (Line = 'END:VEVENT') or (Line = 'END:VTODO') then
      begin
        if InEvent and Assigned(Ev) then
        begin
          if Ev.Summary = '' then Ev.Summary := '(제목 없음)';
          Result.Add(Ev);
        end;
        Ev := nil;
        InEvent := False;
        Continue;
      end;

      if not InEvent or not Assigned(Ev) then Continue;

      P := Pos(':', Line);
      if P = 0 then Continue;
      Key := Copy(Line, 1, P - 1);
      Val := Copy(Line, P + 1, MaxInt);

      // Key 에 파라미터가 붙는 경우 (DTSTART;VALUE=DATE) 대비
      if Pos(';', Key) > 0 then
        Key := Copy(Key, 1, Pos(';', Key) - 1);

      if SameText(Key, 'UID') then
        Ev.UID := Val
      else if SameText(Key, 'SUMMARY') then
        Ev.Summary := DecodeText(Val)
      else if SameText(Key, 'DTSTART') then
        Ev.StartTime := ParseICSDate(Line, Ev.HasTime)
      else if SameText(Key, 'DUE') and Ev.IsTodo then
        Ev.StartTime := ParseICSDate(Line, Ev.HasTime);
    end;

    // BEGIN 은 있었는데 END 를 못 만난 마지막 이벤트 방어
    if InEvent and Assigned(Ev) then
      Ev.Free;

    Result.SortByStart;
  finally
    Lines.Free;
  end;
end;

class function TCalendarFetcher.Fetch(const AUrl: string; out AError: string): TCalEventList;
var
  Http: THTTPClient;
  Resp: IHTTPResponse;
  Url: string;
begin
  Result := nil;
  AError := '';
  Url := Trim(AUrl);
  // webcal:// -> https://
  if Pos('webcal://', LowerCase(Url)) = 1 then
    Url := 'https://' + Copy(Url, 10, MaxInt);

  if Url = '' then
  begin
    AError := 'ICS 주소가 비어 있습니다';
    Exit;
  end;

  Http := THTTPClient.Create;
  try
    try
      Http.ConnectionTimeout := 15000;
      Http.ResponseTimeout := 20000;
      Http.CustomHeaders['User-Agent'] := 'Mozilla/5.0 KakaoScheduler';
      Resp := Http.Get(Url);
      if Resp.StatusCode <> 200 then
      begin
        AError := Format('다운로드 실패 (HTTP %d) - ICS 주소를 확인하세요', [Resp.StatusCode]);
        Exit;
      end;
      Result := ParseICS(Resp.ContentAsString(TEncoding.UTF8));
    except
      on E: Exception do
        AError := '연결 오류: ' + E.Message;
    end;
  finally
    Http.Free;
  end;
end;

class function TCalendarFetcher.FilterRange(ASrc: TCalEventList;
  AFrom, ATo: TDateTime): TCalEventList;
var
  Ev, N: TCalEvent;
begin
  Result := TCalEventList.Create(True);
  for Ev in ASrc do
    if (Ev.StartTime >= AFrom) and (Ev.StartTime < ATo) then
    begin
      N := TCalEvent.Create;
      N.UID := Ev.UID;
      N.Summary := Ev.Summary;
      N.StartTime := Ev.StartTime;
      N.HasTime := Ev.HasTime;
      N.IsTodo := Ev.IsTodo;
      Result.Add(N);
    end;
  Result.SortByStart;
end;

end.
