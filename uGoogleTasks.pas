unit uGoogleTasks;

{
  구글 Tasks 연동 (OAuth 2.0 Desktop / Loopback 방식)

  동작 개요
  ---------
  1. 사용자가 [구글 로그인]을 누르면 로컬 HTTP 서버(127.0.0.1:임의포트)를 띄운다.
  2. 기본 브라우저로 구글 동의 화면을 연다.
  3. 사용자가 동의하면 구글이 http://127.0.0.1:PORT/?code=... 로 리다이렉트한다.
  4. 로컬 서버가 code 를 받아 access_token / refresh_token 으로 교환한다.
  5. refresh_token 을 저장해두고, 이후에는 자동으로 access_token 을 갱신한다.

  필요 사전 준비 (README_GoogleTasks.md 참고)
  ------------------------------------------
  - 구글 클라우드 콘솔에서 "데스크톱 앱" OAuth 클라이언트 생성
  - Client ID / Client Secret 를 프로그램에 입력
  - Tasks API 사용 설정

  주의
  ----
  Client Secret 은 데스크톱 앱에서는 완전한 비밀이 아니다(구글도 이를 전제로 함).
  그래도 외부 노출은 피하고, 프로그램 설정 파일에만 저장한다.
}

interface

uses
  Winapi.Windows, Winapi.ShellAPI,
  System.SysUtils, System.Classes,
  System.NetEncoding, System.JSON, System.DateUtils, System.IOUtils,
  System.Net.HttpClient, System.Net.URLClient, System.Generics.Collections,
  IdHTTPServer, IdContext, IdCustomHTTPServer, IdGlobal;

const
  // Tasks(읽기/쓰기) + Drive(이 앱이 만든 파일만) — 공백으로 구분
  GTASKS_SCOPE = 'https://www.googleapis.com/auth/tasks https://www.googleapis.com/auth/drive.file';
  AUTH_ENDPOINT = 'https://accounts.google.com/o/oauth2/v2/auth';
  TOKEN_ENDPOINT = 'https://oauth2.googleapis.com/token';
  TASKLISTS_URL = 'https://tasks.googleapis.com/tasks/v1/users/@me/lists';
  TASKS_URL_FMT = 'https://tasks.googleapis.com/tasks/v1/lists/%s/tasks?showCompleted=false&maxResults=100';
  TASKS_INSERT_FMT = 'https://tasks.googleapis.com/tasks/v1/lists/%s/tasks';
  TASK_PATCH_FMT = 'https://tasks.googleapis.com/tasks/v1/lists/%s/tasks/%s';

type
  TGoogleTask = class
  public
    Id: string;
    ListId: string;
    Title: string;
    Notes: string;
    Due: TDateTime;
    HasDue: Boolean;
    ListName: string;
    function DisplayText: string;
  end;

  TGoogleTaskList = class(TObjectList<TGoogleTask>);

  TGoogleAuth = class
  private
    FClientId: string;
    FClientSecret: string;
    FRefreshToken: string;
    FAccessToken: string;
    FTokenExpiry: TDateTime;
    FCfgFile: string;
    FServer: TIdHTTPServer;
    FAuthCode: string;
    FGotCode: Boolean;
    FRedirectPort: Integer;
    procedure OnCommandGet(AContext: TIdContext;
      ARequestInfo: TIdHTTPRequestInfo; AResponseInfo: TIdHTTPResponseInfo);
    function ExchangeCode(const ACode: string; out AError: string): Boolean;
    function RefreshAccess(out AError: string): Boolean;
  public
    constructor Create(const ACfgFile: string);
    destructor Destroy; override;

    procedure LoadTokens;
    procedure SaveTokens;
    procedure SetCredentials(const AClientId, AClientSecret: string);
    function ClientId: string;
    function ClientSecret: string;
    function IsConnected: Boolean;    // refresh_token 보유 여부
    procedure Disconnect;

    /// 브라우저 동의 흐름을 시작해 refresh_token 을 얻는다 (동기, 최대 AtimeoutSec 대기)
    function Authorize(ATimeoutSec: Integer; out AError: string): Boolean;

    /// 유효한 access_token 을 반환 (필요 시 자동 갱신)
    function GetValidAccessToken(out AError: string): string;
  end;

  TGoogleTasksFetcher = class
  public
    /// 모든 작업목록의 미완료 할일을 가져온다
    class function FetchAll(AAuth: TGoogleAuth; out AError: string): TGoogleTaskList;

    /// 기본 작업목록 ID (@default). 실패 시 빈 문자열
    class function DefaultListId(AAuth: TGoogleAuth; out AError: string): string;

    /// 새 할일을 구글에 추가한다. ADueDate=0 이면 기한 없음
    class function InsertTask(AAuth: TGoogleAuth; const AListId, ATitle, ANotes: string;
      ADueDate: TDateTime; out AError: string): Boolean;

    /// 할일을 완료 처리한다
    class function CompleteTask(AAuth: TGoogleAuth; const AListId, ATaskId: string;
      out AError: string): Boolean;

    /// 할일의 제목/메모/기한을 수정한다. AHasDue=False 면 기한 삭제
    class function UpdateTask(AAuth: TGoogleAuth; const AListId, ATaskId,
      ATitle, ANotes: string; ADue: TDateTime; AHasDue: Boolean;
      out AError: string): Boolean;

    /// 할일을 삭제한다
    class function DeleteTask(AAuth: TGoogleAuth; const AListId, ATaskId: string;
      out AError: string): Boolean;
  end;

implementation

{ ---------- TGoogleTask ---------- }

function TGoogleTask.DisplayText: string;
begin
  if HasDue then
    Result := FormatDateTime('mm-dd', Due) + '  ' + Title
  else
    Result := '(기한없음)  ' + Title;
  if ListName <> '' then
    Result := Result + '  [' + ListName + ']';
end;

{ ---------- 유틸 ---------- }

function UrlEncode(const S: string): string;
begin
  Result := TNetEncoding.URL.Encode(S);
end;

function GetJsonStr(O: TJSONObject; const K: string): string;
var V: TJSONValue;
begin
  V := O.GetValue(K);
  if (V = nil) or (V is TJSONNull) then Result := '' else Result := V.Value;
end;

{ ---------- TGoogleAuth ---------- }

constructor TGoogleAuth.Create(const ACfgFile: string);
begin
  inherited Create;
  FCfgFile := ACfgFile;
  LoadTokens;
end;

destructor TGoogleAuth.Destroy;
begin
  if Assigned(FServer) then
  begin
    FServer.Active := False;
    FServer.Free;
  end;
  inherited;
end;

procedure TGoogleAuth.LoadTokens;
var
  V: TJSONValue;
  O: TJSONObject;
begin
  if not FileExists(FCfgFile) then Exit;
  V := nil;
  try
    V := TJSONObject.ParseJSONValue(TFile.ReadAllText(FCfgFile, TEncoding.UTF8));
    if V is TJSONObject then
    begin
      O := TJSONObject(V);
      FClientId := GetJsonStr(O, 'client_id');
      FClientSecret := GetJsonStr(O, 'client_secret');
      FRefreshToken := GetJsonStr(O, 'refresh_token');
    end;
  except
  end;
  V.Free;
end;

procedure TGoogleAuth.SaveTokens;
var
  O: TJSONObject;
begin
  O := TJSONObject.Create;
  try
    O.AddPair('client_id', FClientId);
    O.AddPair('client_secret', FClientSecret);
    O.AddPair('refresh_token', FRefreshToken);
    TFile.WriteAllText(FCfgFile, O.ToJSON, TEncoding.UTF8);
  except
  end;
  O.Free;
end;

procedure TGoogleAuth.SetCredentials(const AClientId, AClientSecret: string);
begin
  FClientId := Trim(AClientId);
  FClientSecret := Trim(AClientSecret);
  SaveTokens;
end;

function TGoogleAuth.ClientId: string;
begin
  Result := FClientId;
end;

function TGoogleAuth.ClientSecret: string;
begin
  Result := FClientSecret;
end;

function TGoogleAuth.IsConnected: Boolean;
begin
  Result := FRefreshToken <> '';
end;

procedure TGoogleAuth.Disconnect;
begin
  FRefreshToken := '';
  FAccessToken := '';
  FTokenExpiry := 0;
  SaveTokens;
end;

procedure TGoogleAuth.OnCommandGet(AContext: TIdContext;
  ARequestInfo: TIdHTTPRequestInfo; AResponseInfo: TIdHTTPResponseInfo);
var
  Code, Err: string;
begin
  Code := ARequestInfo.Params.Values['code'];
  Err := ARequestInfo.Params.Values['error'];

  AResponseInfo.ContentType := 'text/html; charset=utf-8';
  if Code <> '' then
  begin
    FAuthCode := Code;
    FGotCode := True;
    AResponseInfo.ContentText :=
      '<html><body style="font-family:sans-serif;text-align:center;padding-top:60px">' +
      '<h2>인증 완료</h2><p>이 창을 닫고 프로그램으로 돌아가세요.</p></body></html>';
  end
  else
    AResponseInfo.ContentText :=
      '<html><body style="font-family:sans-serif;text-align:center;padding-top:60px">' +
      '<h2>인증 실패</h2><p>' + Err + '</p></body></html>';
end;

function TGoogleAuth.Authorize(ATimeoutSec: Integer; out AError: string): Boolean;
var
  Url, Redirect: string;
  Waited: Integer;
begin
  Result := False;
  AError := '';

  if (FClientId = '') or (FClientSecret = '') then
  begin
    AError := 'Client ID / Secret 이 설정되지 않았습니다. 먼저 [구글 설정]에서 입력하세요.';
    Exit;
  end;

  FRedirectPort := 0;
  FGotCode := False;
  FAuthCode := '';

  // 로컬 콜백 서버 기동 - 빈 포트를 찾을 때까지 시도
  FServer := TIdHTTPServer.Create(nil);
  FServer.OnCommandGet := OnCommandGet;
  try
    for var P := 49200 to 49230 do
    begin
      try
        FServer.Bindings.Clear;
        FServer.DefaultPort := P;
        FServer.Active := True;
        FRedirectPort := P;
        Break;
      except
        FServer.Active := False;
      end;
    end;
    if FRedirectPort = 0 then
    begin
      AError := '로컬 콜백 포트를 열 수 없습니다.';
      Exit;
    end;
  except
    on E: Exception do
    begin
      AError := '로컬 서버 시작 실패: ' + E.Message;
      Exit;
    end;
  end;

  Redirect := Format('http://127.0.0.1:%d/', [FRedirectPort]);

  try
    // 동의 화면 URL 구성 후 브라우저 열기
    Url := AUTH_ENDPOINT +
      '?client_id=' + UrlEncode(FClientId) +
      '&redirect_uri=' + UrlEncode(Redirect) +
      '&response_type=code' +
      '&scope=' + UrlEncode(GTASKS_SCOPE) +
      '&access_type=offline' +
      '&prompt=consent';
    ShellExecute(0, 'open', PChar(Url), nil, nil, SW_SHOWNORMAL);

    // code 수신 대기
    Waited := 0;
    while (not FGotCode) and (Waited < ATimeoutSec * 1000) do
    begin
      Sleep(200);
      Inc(Waited, 200);
    end;

    if not FGotCode then
    begin
      AError := '인증 시간이 초과되었습니다. 다시 시도하세요.';
      Exit;
    end;

    Result := ExchangeCode(FAuthCode, AError);
  finally
    FServer.Active := False;
    FreeAndNil(FServer);
  end;
end;

function TGoogleAuth.ExchangeCode(const ACode: string; out AError: string): Boolean;
var
  Http: THTTPClient;
  Params: TStringList;
  Resp: IHTTPResponse;
  O: TJSONValue;
  JO: TJSONObject;
  Redirect: string;
begin
  Result := False;
  Redirect := Format('http://127.0.0.1:%d/', [FRedirectPort]);
  Http := THTTPClient.Create;
  Params := TStringList.Create;
  try
    Params.AddPair('code', ACode);
    Params.AddPair('client_id', FClientId);
    Params.AddPair('client_secret', FClientSecret);
    Params.AddPair('redirect_uri', Redirect);
    Params.AddPair('grant_type', 'authorization_code');
    try
      Resp := Http.Post(TOKEN_ENDPOINT, Params);
      if Resp.StatusCode <> 200 then
      begin
        AError := 'token 교환 실패: ' + Resp.ContentAsString;
        Exit;
      end;
      O := TJSONObject.ParseJSONValue(Resp.ContentAsString(TEncoding.UTF8));
      try
        if O is TJSONObject then
        begin
          JO := TJSONObject(O);
          FAccessToken := GetJsonStr(JO, 'access_token');
          FRefreshToken := GetJsonStr(JO, 'refresh_token');
          FTokenExpiry := IncSecond(Now,
            StrToIntDef(GetJsonStr(JO, 'expires_in'), 3600) - 60);
          SaveTokens;
          Result := FRefreshToken <> '';
          if not Result then
            AError := 'refresh_token 을 받지 못했습니다. 구글 계정 권한을 해제 후 다시 시도하세요.';
        end;
      finally
        O.Free;
      end;
    except
      on E: Exception do
        AError := 'token 교환 오류: ' + E.Message;
    end;
  finally
    Params.Free;
    Http.Free;
  end;
end;

function TGoogleAuth.RefreshAccess(out AError: string): Boolean;
var
  Http: THTTPClient;
  Params: TStringList;
  Resp: IHTTPResponse;
  O: TJSONValue;
  JO: TJSONObject;
begin
  Result := False;
  if FRefreshToken = '' then
  begin
    AError := '연결되지 않았습니다. [구글 로그인]을 먼저 하세요.';
    Exit;
  end;
  Http := THTTPClient.Create;
  Params := TStringList.Create;
  try
    Params.AddPair('client_id', FClientId);
    Params.AddPair('client_secret', FClientSecret);
    Params.AddPair('refresh_token', FRefreshToken);
    Params.AddPair('grant_type', 'refresh_token');
    try
      Resp := Http.Post(TOKEN_ENDPOINT, Params);
      if Resp.StatusCode <> 200 then
      begin
        AError := 'access_token 갱신 실패: ' + Resp.ContentAsString;
        // refresh_token 이 폐기된 경우
        if Pos('invalid_grant', Resp.ContentAsString) > 0 then
        begin
          FRefreshToken := '';
          SaveTokens;
          AError := '구글 연결이 만료되었습니다. 다시 로그인하세요.';
        end;
        Exit;
      end;
      O := TJSONObject.ParseJSONValue(Resp.ContentAsString(TEncoding.UTF8));
      try
        if O is TJSONObject then
        begin
          JO := TJSONObject(O);
          FAccessToken := GetJsonStr(JO, 'access_token');
          FTokenExpiry := IncSecond(Now,
            StrToIntDef(GetJsonStr(JO, 'expires_in'), 3600) - 60);
          Result := FAccessToken <> '';
        end;
      finally
        O.Free;
      end;
    except
      on E: Exception do
        AError := '갱신 오류: ' + E.Message;
    end;
  finally
    Params.Free;
    Http.Free;
  end;
end;

function TGoogleAuth.GetValidAccessToken(out AError: string): string;
begin
  Result := '';
  AError := '';
  if (FAccessToken <> '') and (Now < FTokenExpiry) then
    Exit(FAccessToken);
  if RefreshAccess(AError) then
    Result := FAccessToken;
end;

{ ---------- TGoogleTasksFetcher ---------- }

class function TGoogleTasksFetcher.FetchAll(AAuth: TGoogleAuth;
  out AError: string): TGoogleTaskList;
var
  Http: THTTPClient;
  Token: string;
  Resp: IHTTPResponse;
  V, TV: TJSONValue;
  ListsObj, TasksObj: TJSONObject;
  ListsArr, TasksArr: TJSONArray;
  I, J: Integer;
  ListId, ListTitle, DueStr: string;
  T: TGoogleTask;
  DueDT: TDateTime;
  FS: TFormatSettings;
begin
  Result := TGoogleTaskList.Create(True);
  AError := '';

  Token := AAuth.GetValidAccessToken(AError);
  if Token = '' then
  begin
    if AError = '' then AError := '인증 토큰을 얻지 못했습니다.';
    Exit;
  end;

  FS := TFormatSettings.Invariant;

  Http := THTTPClient.Create;
  try
    Http.CustomHeaders['Authorization'] := 'Bearer ' + Token;

    // 1) 작업목록 조회
    try
      Resp := Http.Get(TASKLISTS_URL);
    except
      on E: Exception do
      begin
        AError := '작업목록 조회 오류: ' + E.Message;
        Exit;
      end;
    end;
    if Resp.StatusCode <> 200 then
    begin
      AError := '작업목록 조회 실패 (HTTP ' + IntToStr(Resp.StatusCode) + ')';
      Exit;
    end;

    V := TJSONObject.ParseJSONValue(Resp.ContentAsString(TEncoding.UTF8));
    if not (V is TJSONObject) then
    begin
      V.Free;
      AError := '작업목록 응답 형식 오류';
      Exit;
    end;
    ListsObj := TJSONObject(V);
    try
      if not (ListsObj.GetValue('items') is TJSONArray) then Exit;
      ListsArr := ListsObj.GetValue('items') as TJSONArray;

      for I := 0 to ListsArr.Count - 1 do
      begin
        if not (ListsArr.Items[I] is TJSONObject) then Continue;
        ListId := GetJsonStr(TJSONObject(ListsArr.Items[I]), 'id');
        ListTitle := GetJsonStr(TJSONObject(ListsArr.Items[I]), 'title');
        if ListId = '' then Continue;

        // 2) 목록별 할일 조회
        try
          Resp := Http.Get(Format(TASKS_URL_FMT, [ListId]));
        except
          Continue;
        end;
        if Resp.StatusCode <> 200 then Continue;

        TV := TJSONObject.ParseJSONValue(Resp.ContentAsString(TEncoding.UTF8));
        if not (TV is TJSONObject) then
        begin
          TV.Free;
          Continue;
        end;
        TasksObj := TJSONObject(TV);
        try
          if not (TasksObj.GetValue('items') is TJSONArray) then Continue;
          TasksArr := TasksObj.GetValue('items') as TJSONArray;

          for J := 0 to TasksArr.Count - 1 do
          begin
            if not (TasksArr.Items[J] is TJSONObject) then Continue;
            T := TGoogleTask.Create;
            T.Id := GetJsonStr(TJSONObject(TasksArr.Items[J]), 'id');
            T.ListId := ListId;
            T.Title := GetJsonStr(TJSONObject(TasksArr.Items[J]), 'title');
            T.Notes := GetJsonStr(TJSONObject(TasksArr.Items[J]), 'notes');
            T.ListName := ListTitle;
            DueStr := GetJsonStr(TJSONObject(TasksArr.Items[J]), 'due');
            // due 는 RFC3339 (예: 2026-08-05T00:00:00.000Z)
            T.HasDue := False;
            if DueStr <> '' then
            begin
              DueDT := 0;
              if TryEncodeDate(
                   StrToIntDef(Copy(DueStr, 1, 4), 0),
                   StrToIntDef(Copy(DueStr, 6, 2), 0),
                   StrToIntDef(Copy(DueStr, 9, 2), 0), DueDT) then
              begin
                T.Due := DueDT;
                T.HasDue := True;
              end;
            end;
            if Trim(T.Title) = '' then
              T.Free
            else
              Result.Add(T);
          end;
        finally
          TV.Free;
        end;
      end;
    finally
      V.Free;
    end;
  finally
    Http.Free;
  end;
end;

class function TGoogleTasksFetcher.DefaultListId(AAuth: TGoogleAuth;
  out AError: string): string;
begin
  // @default 는 구글이 인식하는 기본 목록 별칭
  Result := '@default';
  AError := '';
end;

class function TGoogleTasksFetcher.InsertTask(AAuth: TGoogleAuth;
  const AListId, ATitle, ANotes: string; ADueDate: TDateTime;
  out AError: string): Boolean;
var
  Http: THTTPClient;
  Token, ListId, Body: string;
  Src: TStringStream;
  Resp: IHTTPResponse;
  JO: TJSONObject;
begin
  Result := False;
  AError := '';
  Token := AAuth.GetValidAccessToken(AError);
  if Token = '' then Exit;

  if Trim(AListId) = '' then ListId := '@default' else ListId := AListId;

  JO := TJSONObject.Create;
  try
    JO.AddPair('title', ATitle);
    if Trim(ANotes) <> '' then JO.AddPair('notes', ANotes);
    if ADueDate > 0 then
      // 기한은 RFC3339, 날짜만 있어도 자정 UTC 로 보낸다
      JO.AddPair('due', FormatDateTime('yyyy-mm-dd', ADueDate) + 'T00:00:00.000Z');
    Body := JO.ToJSON;
  finally
    JO.Free;
  end;

  Http := THTTPClient.Create;
  Src := TStringStream.Create(Body, TEncoding.UTF8);
  try
    Http.CustomHeaders['Authorization'] := 'Bearer ' + Token;
    Http.ContentType := 'application/json';
    try
      Resp := Http.Post(Format(TASKS_INSERT_FMT, [ListId]), Src);
      if (Resp.StatusCode = 200) or (Resp.StatusCode = 201) then
        Result := True
      else if Resp.StatusCode = 403 then
        AError := '쓰기 권한이 없습니다 (HTTP 403).' + sLineBreak +
          '기존 로그인은 읽기 전용 권한으로 발급된 토큰입니다.' + sLineBreak +
          '[연동 설정] → [연결 해제] → [구글 로그인] 으로 다시 로그인하세요.'
      else
        AError := '구글 할일 추가 실패 (HTTP ' + IntToStr(Resp.StatusCode) + ')';
    except
      on E: Exception do
        AError := '추가 오류: ' + E.Message;
    end;
  finally
    Src.Free;
    Http.Free;
  end;
end;

class function TGoogleTasksFetcher.CompleteTask(AAuth: TGoogleAuth;
  const AListId, ATaskId: string; out AError: string): Boolean;
var
  Http: THTTPClient;
  Token, Body: string;
  Src: TStringStream;
  Resp: IHTTPResponse;
  JO: TJSONObject;
begin
  Result := False;
  AError := '';
  Token := AAuth.GetValidAccessToken(AError);
  if Token = '' then Exit;
  if (Trim(AListId) = '') or (Trim(ATaskId) = '') then
  begin
    AError := '완료 처리할 항목 정보가 없습니다.';
    Exit;
  end;

  JO := TJSONObject.Create;
  try
    JO.AddPair('status', 'completed');
    Body := JO.ToJSON;
  finally
    JO.Free;
  end;

  Http := THTTPClient.Create;
  Src := TStringStream.Create(Body, TEncoding.UTF8);
  try
    Http.CustomHeaders['Authorization'] := 'Bearer ' + Token;
    Http.ContentType := 'application/json';
    try
      // PATCH 로 status 만 변경
      Resp := Http.Patch(Format(TASK_PATCH_FMT, [AListId, ATaskId]), Src);
      if Resp.StatusCode = 200 then
        Result := True
      else if Resp.StatusCode = 403 then
        AError := '쓰기 권한이 없습니다 (HTTP 403).' + sLineBreak +
          '[연동 설정] → [연결 해제] → [구글 로그인] 으로 다시 로그인하세요.'
      else
        AError := '완료 처리 실패 (HTTP ' + IntToStr(Resp.StatusCode) + ')';
    except
      on E: Exception do
        AError := '완료 처리 오류: ' + E.Message;
    end;
  finally
    Src.Free;
    Http.Free;
  end;
end;

class function TGoogleTasksFetcher.UpdateTask(AAuth: TGoogleAuth;
  const AListId, ATaskId, ATitle, ANotes: string; ADue: TDateTime;
  AHasDue: Boolean; out AError: string): Boolean;
var
  Http: THTTPClient;
  Token, Body: string;
  Src: TStringStream;
  Resp: IHTTPResponse;
  JO: TJSONObject;
begin
  Result := False;
  AError := '';
  Token := AAuth.GetValidAccessToken(AError);
  if Token = '' then Exit;
  if (Trim(AListId) = '') or (Trim(ATaskId) = '') then
  begin
    AError := '수정할 항목 정보가 없습니다.';
    Exit;
  end;

  JO := TJSONObject.Create;
  try
    JO.AddPair('title', ATitle);
    JO.AddPair('notes', ANotes);
    if AHasDue and (ADue > 0) then
      JO.AddPair('due', FormatDateTime('yyyy-mm-dd', ADue) + 'T00:00:00.000Z')
    else
      JO.AddPair('due', TJSONNull.Create);   // 기한 삭제
    Body := JO.ToJSON;
  finally
    JO.Free;
  end;

  Http := THTTPClient.Create;
  Src := TStringStream.Create(Body, TEncoding.UTF8);
  try
    Http.CustomHeaders['Authorization'] := 'Bearer ' + Token;
    Http.ContentType := 'application/json';
    try
      Resp := Http.Patch(Format(TASK_PATCH_FMT, [AListId, ATaskId]), Src);
      if Resp.StatusCode = 200 then
        Result := True
      else if Resp.StatusCode = 403 then
        AError := '쓰기 권한이 없습니다 (HTTP 403).' + sLineBreak +
          '[연동 설정] -> [연결 해제] -> [구글 로그인] 으로 다시 로그인하세요.'
      else
        AError := '수정 실패 (HTTP ' + IntToStr(Resp.StatusCode) + ')';
    except
      on E: Exception do
        AError := '수정 오류: ' + E.Message;
    end;
  finally
    Src.Free;
    Http.Free;
  end;
end;

class function TGoogleTasksFetcher.DeleteTask(AAuth: TGoogleAuth;
  const AListId, ATaskId: string; out AError: string): Boolean;
var
  Http: THTTPClient;
  Token: string;
  Resp: IHTTPResponse;
begin
  Result := False;
  AError := '';
  Token := AAuth.GetValidAccessToken(AError);
  if Token = '' then Exit;
  if (Trim(AListId) = '') or (Trim(ATaskId) = '') then
  begin
    AError := '삭제할 항목 정보가 없습니다.';
    Exit;
  end;

  Http := THTTPClient.Create;
  try
    Http.CustomHeaders['Authorization'] := 'Bearer ' + Token;
    try
      Resp := Http.Delete(Format(TASK_PATCH_FMT, [AListId, ATaskId]));
      if (Resp.StatusCode = 200) or (Resp.StatusCode = 204) then
        Result := True
      else if Resp.StatusCode = 403 then
        AError := '쓰기 권한이 없습니다 (HTTP 403). 다시 로그인하세요.'
      else
        AError := '삭제 실패 (HTTP ' + IntToStr(Resp.StatusCode) + ')';
    except
      on E: Exception do
        AError := '삭제 오류: ' + E.Message;
    end;
  finally
    Http.Free;
  end;
end;

end.