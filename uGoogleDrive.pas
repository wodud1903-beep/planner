unit uGoogleDrive;


interface

uses
  System.SysUtils, System.Classes, System.JSON, System.DateUtils,
  System.Net.HttpClient, System.Net.URLClient,
  uGoogleTasks;

const
  DRIVE_META_URL  = 'https://www.googleapis.com/drive/v3/files';
  DRIVE_MEDIA_FMT = 'https://www.googleapis.com/upload/drive/v3/files/%s?uploadType=media';

type
  TGoogleDrive = class
  public
    /// 텍스트 내용을 지정한 파일명으로 드라이브에 새로 올린다.
    class function UploadText(AAuth: TGoogleAuth; const AFileName, AContent: string;
      out AError: string): Boolean;
  end;

implementation

class function TGoogleDrive.UploadText(AAuth: TGoogleAuth;
  const AFileName, AContent: string; out AError: string): Boolean;
var
  Http: THTTPClient;
  Token, FileId, Body: string;
  Src: TStringStream;
  Resp: IHTTPResponse;
  JO: TJSONObject;
  V: TJSONValue;
begin
  Result := False;
  AError := '';
  FileId := '';

  Token := AAuth.GetValidAccessToken(AError);
  if Token = '' then
  begin
    if AError = '' then AError := '구글 인증이 필요합니다.';
    Exit;
  end;

  // ---------- 1단계: 파일 생성(메타데이터) ----------
  JO := TJSONObject.Create;
  try
    JO.AddPair('name', AFileName);
    JO.AddPair('mimeType', 'application/json');
    Body := JO.ToJSON;
  finally
    JO.Free;
  end;

  Http := THTTPClient.Create;
  Src := TStringStream.Create(Body, TEncoding.UTF8);
  try
    Http.CustomHeaders['Authorization'] := 'Bearer ' + Token;
    Http.ContentType := 'application/json; charset=UTF-8';
    try
      Resp := Http.Post(DRIVE_META_URL, Src);
      if (Resp.StatusCode <> 200) and (Resp.StatusCode <> 201) then
      begin
        if Resp.StatusCode = 403 then
          AError := '드라이브 권한이 없습니다 (HTTP 403).' + sLineBreak +
            '[연동 설정] -> [연결 해제] -> [구글 로그인] 으로 다시 로그인하세요.'
        else
          AError := '드라이브 파일 생성 실패 (HTTP ' + IntToStr(Resp.StatusCode) + ')';
        Exit;
      end;
      V := TJSONObject.ParseJSONValue(Resp.ContentAsString(TEncoding.UTF8));
      try
        if V is TJSONObject then
          FileId := TJSONObject(V).GetValue<string>('id', '');
      finally
        V.Free;
      end;
    except
      on E: Exception do
      begin
        AError := '드라이브 연결 오류: ' + E.Message;
        Exit;
      end;
    end;
  finally
    Src.Free;
    Http.Free;
  end;

  if FileId = '' then
  begin
    AError := '드라이브 파일 ID를 받지 못했습니다.';
    Exit;
  end;

  // ---------- 2단계: 실제 내용 업로드 ----------
  Http := THTTPClient.Create;
  Src := TStringStream.Create(AContent, TEncoding.UTF8);
  try
    Http.CustomHeaders['Authorization'] := 'Bearer ' + Token;
    Http.ContentType := 'application/json; charset=UTF-8';
    try
      Resp := Http.Patch(Format(DRIVE_MEDIA_FMT, [FileId]), Src);
      if Resp.StatusCode = 200 then
        Result := True
      else
        AError := '내용 업로드 실패 (HTTP ' + IntToStr(Resp.StatusCode) + ')';
    except
      on E: Exception do
        AError := '업로드 오류: ' + E.Message;
    end;
  finally
    Src.Free;
    Http.Free;
  end;
end;

end.
