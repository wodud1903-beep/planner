object frmMain: TfrmMain
  Left = 0
  Top = 0
  Caption = 'Kakao Scheduler'
  ClientHeight = 640
  ClientWidth = 940
  Color = clBtnFace
  Visible = False
  Font.Charset = DEFAULT_CHARSET
  Font.Color = clWindowText
  Font.Height = -12
  Font.Name = 'Malgun Gothic'
  Font.Style = []
  Position = poScreenCenter
  OnCloseQuery = FormCloseQuery
  OnCreate = FormCreate
  OnDestroy = FormDestroy
  TextHeight = 15
  object pnlTop: TPanel
    Left = 0
    Top = 0
    Width = 940
    Height = 49
    Align = alTop
    BevelOuter = bvNone
    TabOrder = 0
    object lblStatus: TLabel
      Left = 640
      Top = 17
      Width = 60
      Height = 15
      Caption = 'status'
    end
    object btnAdd: TButton
      Left = 10
      Top = 12
      Width = 75
      Height = 27
      Caption = 'Add'
      TabOrder = 0
      OnClick = btnAddClick
    end
    object btnEdit: TButton
      Left = 91
      Top = 12
      Width = 75
      Height = 27
      Caption = 'Edit'
      TabOrder = 1
      OnClick = btnEditClick
    end
    object btnCopy: TButton
      Left = 172
      Top = 12
      Width = 75
      Height = 27
      Caption = 'Copy'
      TabOrder = 2
      OnClick = btnCopyClick
    end
    object btnDel: TButton
      Left = 253
      Top = 12
      Width = 75
      Height = 27
      Caption = 'Delete'
      TabOrder = 3
      OnClick = btnDelClick
    end
    object btnTest: TButton
      Left = 348
      Top = 12
      Width = 95
      Height = 27
      Caption = 'Send Now'
      TabOrder = 4
      OnClick = btnTestClick
    end
    object btnDiag: TButton
      Left = 449
      Top = 12
      Width = 95
      Height = 27
      Caption = 'Diagnose'
      TabOrder = 5
      OnClick = btnDiagClick
    end
  end
  object pnlOpt: TPanel
    Left = 0
    Top = 591
    Width = 940
    Height = 49
    Align = alBottom
    BevelOuter = bvNone
    TabOrder = 1
    object lblDelay: TLabel
      Left = 10
      Top = 17
      Width = 60
      Height = 15
      Caption = 'delay'
    end
    object lblPaste: TLabel
      Left = 190
      Top = 17
      Width = 60
      Height = 15
      Caption = 'paste'
    end
    object edDelay: TEdit
      Left = 120
      Top = 13
      Width = 60
      Height = 23
      TabOrder = 0
      Text = '400'
    end
    object edPaste: TEdit
      Left = 300
      Top = 13
      Width = 60
      Height = 23
      TabOrder = 1
      Text = '1500'
    end
    object chkStartup: TCheckBox
      Left = 390
      Top = 16
      Width = 200
      Height = 17
      Caption = 'startup'
      TabOrder = 2
      OnClick = chkStartupClick
    end
    object btnClearLog: TButton
      Left = 840
      Top = 12
      Width = 90
      Height = 27
      Caption = 'Clear Log'
      TabOrder = 3
      OnClick = btnClearLogClick
    end
  end
  object mLog: TMemo
    Left = 0
    Top = 401
    Width = 940
    Height = 190
    Align = alBottom
    Font.Charset = DEFAULT_CHARSET
    Font.Color = clWindowText
    Font.Height = -12
    Font.Name = 'Consolas'
    Font.Style = []
    ParentFont = False
    ReadOnly = True
    ScrollBars = ssVertical
    TabOrder = 2
  end
  object splLog: TSplitter
    Left = 0
    Top = 396
    Width = 940
    Height = 5
    Cursor = crVSplit
    Align = alBottom
  end
  object lvItems: TListView
    Left = 0
    Top = 49
    Width = 940
    Height = 347
    Align = alClient
    Columns = <
      item
        Caption = 'On'
        Width = 45
      end
      item
        Caption = 'Title'
        Width = 170
      end
      item
        Caption = 'Room'
        Width = 190
      end
      item
        Caption = 'Time'
        Width = 70
      end
      item
        Caption = 'Repeat'
        Width = 130
      end
      item
        Caption = 'Type'
        Width = 90
      end
      item
        Caption = 'LastRun'
        Width = 160
      end>
    GridLines = True
    ReadOnly = True
    RowSelect = True
    TabOrder = 3
    ViewStyle = vsReport
    OnDblClick = lvItemsDblClick
  end
  object Timer1: TTimer
    Interval = 1000
    OnTimer = Timer1Timer
    Left = 700
    Top = 200
  end
  object dlgOpen: TOpenDialog
    Left = 640
    Top = 200
  end
end
