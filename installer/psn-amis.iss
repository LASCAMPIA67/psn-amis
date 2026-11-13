; Installateur de PSN Amis (Inno Setup 6 : https://jrsoftware.org/ishelp/).
;
; Ne pas compiler directement : « uv run outils/construire.py » fournit la version et
; les chemins (/DVersion, /DSource, /DRacine).
;
; Installation par utilisateur, sans droits administrateur, dans
; %LOCALAPPDATA%\Programs\PSN Amis par défaut (dossier modifiable). Les données de
; l'utilisateur (%LOCALAPPDATA%\PSN Amis) ne sont jamais touchées par une installation
; ou une mise à jour ; la désinstallation propose trois niveaux.

#ifndef Version
  #error Version manquante : utilisez outils/construire.py
#endif
#ifndef Source
  #error Dossier de l'application manquant : utilisez outils/construire.py
#endif
#ifndef Racine
  #define Racine ".."
#endif

#define Nom "PSN Amis"
#define Editeur "LASCAMPIA67"
#define Depot "https://github.com/LASCAMPIA67/psn-amis"
#define Exe "PSN Amis.exe"
#define ExeConsole "PSN Amis console.exe"

[Setup]
; Identifiant stable : ne jamais le changer (mises à niveau, désinstallation).
AppId={{8F3B2C7A-5D41-4E9B-9C6E-2A7F1D3B4C59}
AppName={#Nom}
AppVersion={#Version}
AppVerName={#Nom} {#Version}
AppPublisher={#Editeur}
AppPublisherURL={#Depot}
AppSupportURL={#Depot}/issues
AppUpdatesURL={#Depot}/releases
AppComments=Accepte et gère vos demandes d'amis PlayStation. Projet indépendant de Sony.
DefaultDirName={autopf}\{#Nom}
DefaultGroupName={#Nom}
DisableProgramGroupPage=yes
UsePreviousAppDir=yes
UsePreviousTasks=yes
PrivilegesRequired=lowest
OutputBaseFilename=PSN-Amis-Setup-{#Version}
SetupIconFile={#Racine}\src\psn_amis\ressources\icone.ico
UninstallDisplayIcon={app}\{#Exe}
UninstallDisplayName={#Nom}
InfoBeforeFile={#Racine}\installer\avant-installation.txt
LicenseFile={#Racine}\LICENSE
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
; PSN Amis ouvert : l'installateur et le programme de désinstallation le détectent.
AppMutex=PSNAmis.Application
CloseApplications=yes
RestartApplications=no
ShowLanguageDialog=no
SetupLogging=yes
VersionInfoVersion={#Version}
VersionInfoCompany={#Editeur}
VersionInfoDescription=Installation de {#Nom}
VersionInfoProductName={#Nom}
VersionInfoProductVersion={#Version}

[Languages]
Name: "fr"; MessagesFile: "compiler:Languages\French.isl"

[Tasks]
Name: "bureau"; Description: "Créer un raccourci sur le Bureau"; GroupDescription: "Raccourcis :"; Flags: unchecked

[InstallDelete]
; Une mise à niveau remplace entièrement les bibliothèques de l'ancienne version.
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "{#Source}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; Licences visibles à la racine du dossier d'installation.
Source: "{#Source}\_internal\LICENCES-TIERS.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#Source}\_internal\LICENSE"; DestDir: "{app}"; DestName: "LICENCE.txt"; Flags: ignoreversion

[Icons]
Name: "{group}\{#Nom}"; Filename: "{app}\{#Exe}"; Comment: "Accepte et gère vos demandes d'amis PlayStation"
Name: "{group}\Désinstaller {#Nom}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#Nom}"; Filename: "{app}\{#Exe}"; Tasks: bureau

[Run]
Filename: "{app}\{#Exe}"; Description: "Lancer {#Nom}"; Flags: nowait postinstall skipifsilent
; Après une mise à jour lancée depuis l'application (/RELANCER=1, installation silencieuse).
Filename: "{app}\{#Exe}"; Flags: nowait; Check: Relancer

[Code]
const
  CIBLE_CODE = 'PSN Amis/npsso';
  MARQUEUR = 'psn-amis.donnees';

var
  Niveau: Integer;
  EffacerCode: Boolean;

function Relancer: Boolean;
begin
  Result := ExpandConstant('{param:RELANCER|0}') = '1';
end;

{ ─── Données de l'utilisateur ─── }

function DossierDonnees: String;
begin
  { /DONNEES= sert seulement aux tests automatiques ; le dossier doit de toute façon
    contenir le fichier témoin de PSN Amis pour que quoi que ce soit y soit effacé. }
  Result := ExpandConstant('{param:DONNEES|}');
  if Result = '' then
    Result := ExpandConstant('{localappdata}\PSN Amis');
end;

function CibleCode: String;
var
  Test: String;
begin
  Test := ExpandConstant('{param:CIBLE|}');
  if ExpandConstant('{param:DONNEES|}') <> '' then
  begin
    { Mode test (dossier des données forcé) : seule une entrée de test peut être
      retirée, jamais le vrai code, même si /CIBLE= est absent ou mal écrit. }
    Result := '';
    if Pos('PSN Amis/test', Test) = 1 then
      Result := Test;
  end
  else
    Result := CIBLE_CODE;
end;

procedure Effacer(const Dossier, Nom: String);
begin
  if FileExists(Dossier + '\' + Nom) then
    if not DeleteFile(Dossier + '\' + Nom) then
      Log('Suppression impossible : ' + Nom);
end;

procedure EffacerDonnees(AvecCode: Boolean);
var
  Dossier: String;
  I: Integer;
begin
  Dossier := DossierDonnees();
  if not FileExists(Dossier + '\' + MARQUEUR) then
  begin
    Log('Dossier des données sans fichier témoin : rien n''est supprimé (' + Dossier + ').');
    Exit;
  end;
  { Uniquement des fichiers et dossiers créés par PSN Amis, nommés un par un. }
  Effacer(Dossier, 'reglages.toml');
  Effacer(Dossier, 'reglages.toml.bak');
  Effacer(Dossier, 'reglages.toml.tmp');
  Effacer(Dossier, 'reglages.v1.toml');
  Effacer(Dossier, 'journal.txt');
  for I := 1 to 20 do
    Effacer(Dossier, 'journal.txt.' + IntToStr(I));
  Effacer(Dossier, 'diagnostic.txt');
  Effacer(Dossier, 'diagnostic.txt.1');
  Effacer(Dossier, 'amis.json');
  Effacer(Dossier, 'migration.json');
  Effacer(Dossier, 'psn-amis.lock');
  if AvecCode then
    Effacer(Dossier, 'npsso.txt');
  if DirExists(Dossier + '\comptes') then
    DelTree(Dossier + '\comptes', True, True, True);
  if DirExists(Dossier + '\mises_a_jour') then
    DelTree(Dossier + '\mises_a_jour', True, True, True);
  Effacer(Dossier, MARQUEUR);
  { Le dossier n'est retiré que s'il est vide (un fichier ajouté par l'utilisateur
    est conservé). }
  RemoveDir(Dossier);
end;

procedure EffacerCodeEnregistre;
var
  Code: Integer;
begin
  if CibleCode() = '' then
  begin
    Log('Mode test sans entrée de test : aucun code retiré.');
    Exit;
  end;
  { Seule l'entrée de PSN Amis est retirée du Gestionnaire d'identification, avec le
    programme lui-même (encore présent à ce moment de la désinstallation). }
  if Exec(ExpandConstant('{app}\{#ExeConsole}'),
          '--effacer-code --cible "' + CibleCode() + '"', '',
          SW_HIDE, ewWaitUntilTerminated, Code) and (Code = 0) then
    Log('Code npsso retiré du Gestionnaire d''identification.')
  else
    Log('Code npsso : suppression impossible (code ' + IntToStr(Code) + ').');
end;

{ ─── Choix du niveau de désinstallation ─── }

function Texte(Parent: TSetupForm; Haut: Integer; const Contenu: String): TNewStaticText;
begin
  Result := TNewStaticText.Create(Parent);
  Result.Parent := Parent;
  Result.Left := ScaleX(16);
  Result.Top := Haut;
  Result.Width := Parent.ClientWidth - ScaleX(32);
  Result.WordWrap := True;
  Result.Caption := Contenu;
end;

function Choix(Parent: TSetupForm; Haut: Integer; const Contenu: String): TNewRadioButton;
begin
  Result := TNewRadioButton.Create(Parent);
  Result.Parent := Parent;
  Result.Left := ScaleX(16);
  Result.Top := Haut;
  Result.Width := Parent.ClientWidth - ScaleX(32);
  Result.Height := ScaleY(20);
  Result.Caption := Contenu;
end;

function ChoisirNiveau: Boolean;
var
  Fenetre: TSetupForm;
  Standard, AvecDonnees, Complete: TNewRadioButton;
  Code: TNewCheckBox;
  Ok, Annuler: TNewButton;
begin
  Fenetre := CreateCustomForm(ScaleX(560), ScaleY(400), False, True);
  try
    Fenetre.Caption := 'Désinstaller PSN Amis';
    Fenetre.Position := poScreenCenter;
    Texte(Fenetre, ScaleY(14), 'Que souhaitez-vous supprimer ?');
    Standard := Choix(Fenetre, ScaleY(44), '1. Le programme seulement (recommandé)');
    Texte(Fenetre, ScaleY(66), 'Retire le programme et ses raccourcis. Vos réglages, journaux, amis protégés et votre compte connecté sont gardés pour une réinstallation.');
    AvecDonnees := Choix(Fenetre, ScaleY(116), '2. Le programme et vos données');
    Texte(Fenetre, ScaleY(138), 'Retire aussi les réglages, journaux, amis connus, amis protégés et l''historique (dossier ' + DossierDonnees() + ').');
    Complete := Choix(Fenetre, ScaleY(188), '3. Tout, y compris le compte PSN connecté');
    Texte(Fenetre, ScaleY(210), 'Comme le niveau 2, et retire le code npsso de PSN Amis du Gestionnaire d''identification de Windows (rien d''autre dans ce coffre).');
    Code := TNewCheckBox.Create(Fenetre);
    Code.Parent := Fenetre;
    Code.Left := ScaleX(16);
    Code.Top := ScaleY(266);
    Code.Width := Fenetre.ClientWidth - ScaleX(32);
    Code.Height := ScaleY(20);
    Code.Caption := 'Retirer aussi le code npsso enregistré (compte PSN connecté)';
    Texte(Fenetre, ScaleY(292), 'Aucun fichier n''appartenant pas à PSN Amis n''est supprimé. Python, uv et les autres programmes ne sont jamais touchés.');
    Standard.Checked := True;

    Ok := TNewButton.Create(Fenetre);
    Ok.Parent := Fenetre;
    Ok.Caption := 'Désinstaller';
    Ok.ModalResult := mrOk;
    Ok.Default := True;
    Annuler := TNewButton.Create(Fenetre);
    Annuler.Parent := Fenetre;
    Annuler.Caption := 'Annuler';
    Annuler.ModalResult := mrCancel;
    Annuler.Cancel := True;
    Ok.Width := Fenetre.CalculateButtonWidth([Ok.Caption, Annuler.Caption]);
    Annuler.Width := Ok.Width;
    Ok.Height := ScaleY(25);
    Annuler.Height := ScaleY(25);
    Annuler.Left := Fenetre.ClientWidth - Annuler.Width - ScaleX(16);
    Ok.Left := Annuler.Left - Ok.Width - ScaleX(8);
    Ok.Top := Fenetre.ClientHeight - ScaleY(25 + 14);
    Annuler.Top := Ok.Top;
    Fenetre.ActiveControl := Standard;

    Result := Fenetre.ShowModal() = mrOk;
    if Result then
    begin
      if Complete.Checked then Niveau := 3
      else if AvecDonnees.Checked then Niveau := 2
      else Niveau := 1;
      EffacerCode := (Niveau = 3) or Code.Checked;
      if Niveau >= 2 then
        Result := MsgBox('Vos données de PSN Amis seront supprimées définitivement. Continuer ?',
                         mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES;
    end;
  finally
    Fenetre.Free();
  end;
end;

function InitializeUninstall: Boolean;
begin
  Niveau := StrToIntDef(ExpandConstant('{param:NIVEAU|1}'), 1);
  if (Niveau < 1) or (Niveau > 3) then
    Niveau := 1;
  EffacerCode := (Niveau = 3) or (ExpandConstant('{param:IDENTIFIANT|0}') = '1');
  if UninstallSilent() then
    Result := True
  else
    Result := ChoisirNiveau();
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  { Avant la suppression des fichiers : le programme sert encore à retirer le code. }
  if (CurUninstallStep = usUninstall) and EffacerCode then
    EffacerCodeEnregistre();
  if (CurUninstallStep = usPostUninstall) and (Niveau >= 2) then
    EffacerDonnees(EffacerCode);
end;
