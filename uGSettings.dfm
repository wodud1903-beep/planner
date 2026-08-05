object frmGSettings: TfrmGSettings
  Left = 0
  Top = 0
  BorderStyle = bsDialog
  Caption = 'settings'
  ClientHeight = 340
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
  object gbCal: TGroupBox
    Left = 16
    Top = 12
    Width = 528
    Height = 90
    Caption = 'cal'
    TabOrder = 0
    object lblCalUrl: TLabel
      Left = 16
      Top = 30
      Width = 80
      Height = 15
      Caption = 'url'
    end
    object edCalUrl: TEdit
      Left = 16
      Top = 50
      Width = 496
      Height = 23
      TabOrder = 0
    end
  end
  object gbTasks: TGroupBox
    Left = 16
    Top = 112
    Width = 528
    Height = 160
    Caption = 'tasks'
    TabOrder = 1
    object lblStatus: TLabel
      Left = 16
      Top = 28
      Width = 60
      Height = 15
      Caption = 'status'
    end
    object lblStatusVal: TLabel
      Left = 120
      Top = 28
      Width = 200
      Height = 15
      Caption = '-'
    end
    object lblCid: TLabel
      Left = 16
      Top = 58
      Width = 80
      Height = 15
      Caption = 'client id'
    end
    object edCid: TEdit
      Left = 120
      Top = 54
      Width = 392
      Height = 23
      TabOrder = 0
    end
    object lblCsec: TLabel
      Left = 16
      Top = 90
      Width = 80
      Height = 15
      Caption = 'client secret'
    end
    object edCsec: TEdit
      Left = 120
      Top = 86
      Width = 392
      Height = 23
      PasswordChar = '*'
      TabOrder = 1
    end
    object btnLogin: TButton
      Left = 120
      Top = 120
      Width = 120
      Height = 28
      Caption = 'login'
      TabOrder = 2
      OnClick = btnLoginClick
    end
    object btnLogout: TButton
      Left = 248
      Top = 120
      Width = 120
      Height = 28
      Caption = 'logout'
      TabOrder = 3
      OnClick = btnLogoutClick
    end
    object btnHelp: TButton
      Left = 392
      Top = 120
      Width = 120
      Height = 28
      Caption = 'help'
      TabOrder = 4
      OnClick = btnHelpClick
    end
  end
  object btnOK: TButton
    Left = 360
    Top = 300
    Width = 90
    Height = 30
    Caption = 'OK'
    Default = True
    ModalResult = 1
    TabOrder = 2
  end
  object btnCancel: TButton
    Left = 454
    Top = 300
    Width = 90
    Height = 30
    Cancel = True
    Caption = 'Cancel'
    ModalResult = 2
    TabOrder = 3
  end
end
