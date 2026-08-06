object frmGSettings: TfrmGSettings
  Left = 0
  Top = 0
  BorderIcons = [biSystemMenu]
  BorderStyle = bsSingle
  Caption = 'settings'
  ClientHeight = 470
  ClientWidth = 600
  Color = clBtnFace
  Font.Charset = DEFAULT_CHARSET
  Font.Color = clWindowText
  Font.Height = -12
  Font.Name = 'Malgun Gothic'
  Font.Style = []
  Position = poMainFormCenter
  OnCreate = FormCreate
  TextHeight = 15
  object pgc: TPageControl
    Left = 12
    Top = 12
    Width = 576
    Height = 410
    ActivePage = tsGoogle
    TabOrder = 0
    object tsGoogle: TTabSheet
      Caption = 'google'
      object gbCal: TGroupBox
        Left = 12
        Top = 12
        Width = 544
        Height = 86
        Caption = 'cal'
        TabOrder = 0
        object lblCalUrl: TLabel
          Left = 16
          Top = 26
          Width = 80
          Height = 15
          Caption = 'url'
        end
        object edCalUrl: TEdit
          Left = 16
          Top = 46
          Width = 512
          Height = 23
          TabOrder = 0
        end
      end
      object gbTasks: TGroupBox
        Left = 12
        Top = 108
        Width = 544
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
        object lblCsec: TLabel
          Left = 16
          Top = 90
          Width = 80
          Height = 15
          Caption = 'client secret'
        end
        object edCid: TEdit
          Left = 120
          Top = 54
          Width = 408
          Height = 23
          TabOrder = 0
        end
        object edCsec: TEdit
          Left = 120
          Top = 86
          Width = 408
          Height = 23
          PasswordChar = '*'
          TabOrder = 1
        end
        object btnLogin: TButton
          Left = 120
          Top = 120
          Width = 124
          Height = 28
          Caption = 'login'
          TabOrder = 2
          OnClick = btnLoginClick
        end
        object btnLogout: TButton
          Left = 252
          Top = 120
          Width = 124
          Height = 28
          Caption = 'logout'
          TabOrder = 3
          OnClick = btnLogoutClick
        end
        object btnHelp: TButton
          Left = 404
          Top = 120
          Width = 124
          Height = 28
          Caption = 'help'
          TabOrder = 4
          OnClick = btnHelpClick
        end
      end
    end
    object tsFollow: TTabSheet
      Caption = 'follow'
      ImageIndex = 1
      object lblFollowHint: TLabel
        Left = 16
        Top = 14
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
      object chkFollowOn: TCheckBox
        Left = 16
        Top = 40
        Width = 400
        Height = 17
        Caption = 'followon'
        Checked = True
        State = cbChecked
        TabOrder = 0
      end
      object lblKeyword: TLabel
        Left = 16
        Top = 74
        Width = 90
        Height = 15
        Caption = 'keyword'
      end
      object edKeyword: TEdit
        Left = 120
        Top = 70
        Width = 130
        Height = 23
        TabOrder = 1
      end
      object lblMonths: TLabel
        Left = 274
        Top = 74
        Width = 60
        Height = 15
        Caption = 'months'
      end
      object edMonths: TEdit
        Left = 348
        Top = 70
        Width = 60
        Height = 23
        TabOrder = 2
        Text = '1'
      end
      object chkFollowAlarm: TCheckBox
        Left = 250
        Top = 108
        Width = 290
        Height = 17
        Caption = 'followalarm'
        Checked = True
        State = cbChecked
        TabOrder = 5
      end
      object lblFollowTime: TLabel
        Left = 16
        Top = 110
        Width = 90
        Height = 15
        Caption = 'time'
      end
      object dtFollowTime: TDateTimePicker
        Left = 120
        Top = 106
        Width = 110
        Height = 23
        Date = 45000.000000000000000000
        Time = 0.416666666666666700
        Kind = dtkTime
        TabOrder = 3
      end
      object lblFollowMent: TLabel
        Left = 16
        Top = 146
        Width = 200
        Height = 15
        Caption = 'ment'
      end
      object mFollowMent: TMemo
        Left = 16
        Top = 166
        Width = 528
        Height = 180
        ScrollBars = ssVertical
        TabOrder = 4
      end
    end
    object tsHotkey: TTabSheet
      Caption = 'hotkey'
      ImageIndex = 2
      object lblHotHint: TLabel
        Left = 16
        Top = 14
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
      object chkHotOn: TCheckBox
        Left = 16
        Top = 44
        Width = 400
        Height = 17
        Caption = 'hoton'
        Checked = True
        State = cbChecked
        TabOrder = 0
      end
      object gbCombo: TGroupBox
        Left = 16
        Top = 76
        Width = 528
        Height = 90
        Caption = 'combo'
        TabOrder = 1
        object chkCtrl: TCheckBox
          Left = 20
          Top = 34
          Width = 70
          Height = 17
          Caption = 'Ctrl'
          Checked = True
          State = cbChecked
          TabOrder = 0
        end
        object chkAlt: TCheckBox
          Left = 100
          Top = 34
          Width = 70
          Height = 17
          Caption = 'Alt'
          Checked = True
          State = cbChecked
          TabOrder = 1
        end
        object chkShift: TCheckBox
          Left = 180
          Top = 34
          Width = 70
          Height = 17
          Caption = 'Shift'
          TabOrder = 2
        end
        object lblKey: TLabel
          Left = 270
          Top = 36
          Width = 30
          Height = 15
          Caption = 'key'
        end
        object cbKey: TComboBox
          Left = 310
          Top = 32
          Width = 90
          Height = 23
          Style = csDropDownList
          TabOrder = 3
        end
      end
      object lblPreview: TLabel
        Left = 16
        Top = 180
        Width = 300
        Height = 19
        Caption = 'preview'
        Font.Charset = DEFAULT_CHARSET
        Font.Color = clWindowText
        Font.Height = -16
        Font.Name = 'Malgun Gothic'
        Font.Style = [fsBold]
        ParentFont = False
      end
    end
  end
  object btnOK: TButton
    Left = 396
    Top = 432
    Width = 90
    Height = 30
    Caption = 'OK'
    Default = True
    ModalResult = 1
    TabOrder = 1
  end
  object btnCancel: TButton
    Left = 494
    Top = 432
    Width = 94
    Height = 30
    Cancel = True
    Caption = 'Cancel'
    ModalResult = 2
    TabOrder = 2
  end
end
