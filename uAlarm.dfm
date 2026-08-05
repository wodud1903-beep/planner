object frmAlarm: TfrmAlarm
  Left = 0
  Top = 0
  BorderStyle = bsNone
  ClientHeight = 312
  ClientWidth = 620
  Color = 3487029
  Font.Charset = DEFAULT_CHARSET
  Font.Color = clWindowText
  Font.Height = -12
  Font.Name = 'Segoe UI'
  Font.Style = []
  FormStyle = fsStayOnTop
  Position = poDesigned
  OnCreate = FormCreate
  TextHeight = 15
  object lblTitle: TLabel
    Left = 18
    Top = 58
    Width = 40
    Height = 30
    Caption = 'title'
    Font.Charset = DEFAULT_CHARSET
    Font.Color = clWhite
    Font.Height = -22
    Font.Name = 'Malgun Gothic'
    Font.Style = [fsBold]
    ParentFont = False
  end
  object pnlBar: TPanel
    Left = 0
    Top = 0
    Width = 620
    Height = 46
    Align = alTop
    BevelOuter = bvNone
    Color = 2039583
    ParentBackground = False
    TabOrder = 0
    object lblHead: TLabel
      Left = 16
      Top = 11
      Width = 50
      Height = 25
      Caption = 'alarm'
      Font.Charset = DEFAULT_CHARSET
      Font.Color = clWhite
      Font.Height = -19
      Font.Name = 'Malgun Gothic'
      Font.Style = [fsBold]
      ParentFont = False
    end
    object btnClose: TButton
      Left = 574
      Top = 8
      Width = 38
      Height = 30
      Caption = 'X'
      TabOrder = 0
      OnClick = btnCloseClick
    end
  end
  object mMent: TMemo
    Left = 18
    Top = 96
    Width = 584
    Height = 145
    Color = 4210752
    Font.Charset = DEFAULT_CHARSET
    Font.Color = clWhite
    Font.Height = -16
    Font.Name = 'Malgun Gothic'
    Font.Style = []
    ParentFont = False
    ReadOnly = True
    ScrollBars = ssVertical
    TabOrder = 1
  end
  object btnCopy: TButton
    Left = 18
    Top = 254
    Width = 284
    Height = 40
    Caption = 'Copy'
    Font.Charset = DEFAULT_CHARSET
    Font.Color = clWindowText
    Font.Height = -15
    Font.Name = 'Malgun Gothic'
    Font.Style = [fsBold]
    ParentFont = False
    TabOrder = 2
    OnClick = btnCopyClick
  end
  object btnDismiss: TButton
    Left = 318
    Top = 254
    Width = 284
    Height = 40
    Caption = 'Dismiss'
    Font.Charset = DEFAULT_CHARSET
    Font.Color = clWindowText
    Font.Height = -15
    Font.Name = 'Malgun Gothic'
    Font.Style = [fsBold]
    ParentFont = False
    TabOrder = 3
    OnClick = btnDismissClick
  end
  object Timer1: TTimer
    Interval = 600
    OnTimer = Timer1Timer
    Left = 520
    Top = 56
  end
end
