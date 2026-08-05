object frmEditItem: TfrmEditItem
  Left = 0
  Top = 0
  BorderStyle = bsDialog
  Caption = 'Edit Schedule'
  ClientHeight = 540
  ClientWidth = 560
  Color = clBtnFace
  Font.Charset = DEFAULT_CHARSET
  Font.Color = clWindowText
  Font.Height = -12
  Font.Name = 'Malgun Gothic'
  Font.Style = []
  Position = poMainFormCenter
  OnCreate = FormCreate
  TextHeight = 15
  object lblTitle: TLabel
    Left = 16
    Top = 19
    Width = 80
    Height = 15
    Caption = 'title'
  end
  object lblRoom: TLabel
    Left = 16
    Top = 55
    Width = 80
    Height = 15
    Caption = 'room'
  end
  object lblText: TLabel
    Left = 16
    Top = 128
    Width = 80
    Height = 15
    Caption = 'text'
  end
  object lblImage: TLabel
    Left = 16
    Top = 296
    Width = 80
    Height = 15
    Caption = 'image'
  end
  object lblTime: TLabel
    Left = 300
    Top = 340
    Width = 60
    Height = 15
    Caption = 'time'
  end
  object lblHint: TLabel
    Left = 16
    Top = 91
    Width = 500
    Height = 15
    Caption = 'hint'
    Font.Charset = DEFAULT_CHARSET
    Font.Color = clGrayText
    Font.Height = -11
    Font.Name = 'Malgun Gothic'
    Font.Style = []
    ParentFont = False
  end
  object edTitle: TEdit
    Left = 110
    Top = 16
    Width = 430
    Height = 23
    TabOrder = 0
  end
  object cbRoom: TComboBox
    Left = 110
    Top = 52
    Width = 330
    Height = 23
    TabOrder = 1
  end
  object btnRefreshRooms: TButton
    Left = 448
    Top = 51
    Width = 92
    Height = 25
    Caption = 'Refresh'
    TabOrder = 2
    OnClick = btnRefreshRoomsClick
  end
  object mText: TMemo
    Left = 110
    Top = 125
    Width = 430
    Height = 120
    ScrollBars = ssVertical
    TabOrder = 3
  end
  object rgType: TRadioGroup
    Left = 110
    Top = 251
    Width = 430
    Height = 40
    Columns = 2
    ItemIndex = 0
    Items.Strings = (
      'Text'
      'Text + Image')
    TabOrder = 4
    OnClick = rgTypeClick
  end
  object edImage: TEdit
    Left = 110
    Top = 293
    Width = 330
    Height = 23
    TabOrder = 5
  end
  object btnBrowse: TButton
    Left = 448
    Top = 292
    Width = 92
    Height = 25
    Caption = 'Browse'
    TabOrder = 6
    OnClick = btnBrowseClick
  end
  object rgRepeat: TRadioGroup
    Left = 16
    Top = 330
    Width = 260
    Height = 100
    Columns = 1
    ItemIndex = 1
    Items.Strings = (
      'Once'
      'Daily'
      'Weekly')
    TabOrder = 7
    OnClick = rgRepeatClick
  end
  object dtDate: TDateTimePicker
    Left = 300
    Top = 380
    Width = 130
    Height = 23
    Date = 45000.000000000000000000
    Time = 0.500000000000000000
    TabOrder = 9
  end
  object dtTime: TDateTimePicker
    Left = 300
    Top = 336
    Width = 100
    Height = 23
    Date = 45000.000000000000000000
    Time = 0.375000000000000000
    Kind = dtkTime
    TabOrder = 8
  end
  object gbDays: TGroupBox
    Left = 16
    Top = 440
    Width = 524
    Height = 55
    Caption = 'Weekdays'
    TabOrder = 10
    object chkD1: TCheckBox
      Left = 16
      Top = 24
      Width = 50
      Height = 17
      Caption = 'D1'
      TabOrder = 0
    end
    object chkD2: TCheckBox
      Left = 88
      Top = 24
      Width = 50
      Height = 17
      Caption = 'D2'
      TabOrder = 1
    end
    object chkD3: TCheckBox
      Left = 160
      Top = 24
      Width = 50
      Height = 17
      Caption = 'D3'
      TabOrder = 2
    end
    object chkD4: TCheckBox
      Left = 232
      Top = 24
      Width = 50
      Height = 17
      Caption = 'D4'
      TabOrder = 3
    end
    object chkD5: TCheckBox
      Left = 304
      Top = 24
      Width = 50
      Height = 17
      Caption = 'D5'
      TabOrder = 4
    end
    object chkD6: TCheckBox
      Left = 376
      Top = 24
      Width = 50
      Height = 17
      Caption = 'D6'
      TabOrder = 5
    end
    object chkD7: TCheckBox
      Left = 448
      Top = 24
      Width = 50
      Height = 17
      Caption = 'D7'
      TabOrder = 6
    end
  end
  object chkEnabled: TCheckBox
    Left = 300
    Top = 415
    Width = 240
    Height = 17
    Caption = 'enabled'
    Checked = True
    State = cbChecked
    TabOrder = 11
  end
  object btnOK: TButton
    Left = 350
    Top = 503
    Width = 90
    Height = 28
    Caption = 'OK'
    TabOrder = 12
    OnClick = btnOKClick
  end
  object btnCancel: TButton
    Left = 450
    Top = 503
    Width = 90
    Height = 28
    Cancel = True
    Caption = 'Cancel'
    ModalResult = 2
    TabOrder = 13
  end
  object dlgImage: TOpenDialog
    Filter = 'Images|*.png;*.jpg;*.jpeg;*.bmp|All files|*.*'
    Left = 240
    Top = 500
  end
end
