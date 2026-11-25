; FRISTY AI - Windows installer (NSIS 3, Unicode).
; Per-user install: no administrator rights / UAC prompt required.
; Build: makensis -DVERSION=0.1.0 -DSRC=..\desktop\release\win-unpacked installer\fristy.nsi
Unicode true
ManifestDPIAware true
SetCompressor /SOLID lzma
SetCompressorDictSize 64

!ifndef VERSION
  !define VERSION "0.1.0"
!endif
!ifndef SRC
  !define SRC "..\desktop\release\win-unpacked"
!endif
!ifndef OUTDIR
  !define OUTDIR "..\desktop\release"
!endif
!define APPNAME "FRISTY AI"
!define EXENAME "FRISTY AI.exe"
!define UNINSTKEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\FRISTYAI"
!define APPUSERMODELID "ai.fristy.desktop"

Name "${APPNAME}"
OutFile "${OUTDIR}\FRISTY-AI-Setup-${VERSION}-x64.exe"
InstallDir "$LOCALAPPDATA\Programs\${APPNAME}"
InstallDirRegKey HKCU "${UNINSTKEY}" "InstallLocation"
RequestExecutionLevel user
BrandingText "FRISTY AI ${VERSION}"
VIProductVersion "${VERSION}.0"
VIAddVersionKey "ProductName" "${APPNAME}"
VIAddVersionKey "FileDescription" "${APPNAME} Setup"
VIAddVersionKey "FileVersion" "${VERSION}"
VIAddVersionKey "ProductVersion" "${VERSION}"
VIAddVersionKey "CompanyName" "FRISTY"
VIAddVersionKey "LegalCopyright" "FRISTY"

!include "MUI2.nsh"
!include "x64.nsh"
!include "LogicLib.nsh"
!include "WinVer.nsh"

!define MUI_ICON "..\desktop\build\icon.ico"
!define MUI_UNICON "..\desktop\build\icon.ico"
!define MUI_ABORTWARNING
!define MUI_WELCOMEPAGE_TITLE "Welcome to FRISTY AI"
!define MUI_WELCOMEPAGE_TEXT "FRISTY AI is an intelligent desktop assistant that can chat, listen, see your screen (with permission) and safely control your PC.$\r$\n$\r$\nAll computer actions are permission-controlled, audited, and high-risk actions always ask for your approval.$\r$\n$\r$\nRequirements: Windows 10/11 64-bit. For a local AI model, install Ollama from ollama.com (optional - cloud providers are also supported).$\r$\n$\r$\nClick Next to continue."
!define MUI_FINISHPAGE_RUN "$INSTDIR\${EXENAME}"
!define MUI_FINISHPAGE_RUN_TEXT "Launch FRISTY AI"
!define MUI_FINISHPAGE_LINK "Get Ollama (local AI models)"
!define MUI_FINISHPAGE_LINK_LOCATION "https://ollama.com/download"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_COMPONENTS
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "English"
!insertmacro MUI_LANGUAGE "Hebrew"

Function .onInit
  ${IfNot} ${RunningX64}
    MessageBox MB_ICONSTOP "FRISTY AI requires 64-bit Windows 10 or 11."
    Abort
  ${EndIf}
  ${IfNot} ${AtLeastWin10}
    MessageBox MB_ICONSTOP "FRISTY AI requires Windows 10 or newer."
    Abort
  ${EndIf}
FunctionEnd

Function .onInstSuccess
  ; Silent installs are used by the in-app updater: start FRISTY again afterwards.
  IfSilent 0 +2
    Exec '"$INSTDIR\${EXENAME}"'
FunctionEnd

Section "FRISTY AI" SecMain
  SectionIn RO
  ; Stop a running copy so files can be replaced.
  nsExec::Exec 'taskkill /IM "${EXENAME}" /T'
  Sleep 800
  SetOutPath "$INSTDIR"
  ; Remove the previous app/runtime so stale files never linger after upgrades.
  RMDir /r "$INSTDIR\resources"
  File /r "${SRC}\*"
  WriteUninstaller "$INSTDIR\Uninstall FRISTY AI.exe"

  CreateDirectory "$SMPROGRAMS\${APPNAME}"
  CreateShortCut "$SMPROGRAMS\${APPNAME}\${APPNAME}.lnk" "$INSTDIR\${EXENAME}" "" "$INSTDIR\${EXENAME}" 0
  CreateShortCut "$SMPROGRAMS\${APPNAME}\Uninstall ${APPNAME}.lnk" "$INSTDIR\Uninstall FRISTY AI.exe"
  CreateShortCut "$DESKTOP\${APPNAME}.lnk" "$INSTDIR\${EXENAME}" "" "$INSTDIR\${EXENAME}" 0

  WriteRegStr HKCU "${UNINSTKEY}" "DisplayName" "${APPNAME}"
  WriteRegStr HKCU "${UNINSTKEY}" "DisplayVersion" "${VERSION}"
  WriteRegStr HKCU "${UNINSTKEY}" "Publisher" "FRISTY"
  WriteRegStr HKCU "${UNINSTKEY}" "DisplayIcon" "$INSTDIR\${EXENAME}"
  WriteRegStr HKCU "${UNINSTKEY}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "${UNINSTKEY}" "UninstallString" '"$INSTDIR\Uninstall FRISTY AI.exe"'
  WriteRegStr HKCU "${UNINSTKEY}" "QuietUninstallString" '"$INSTDIR\Uninstall FRISTY AI.exe" /S'
  WriteRegDWORD HKCU "${UNINSTKEY}" "NoModify" 1
  WriteRegDWORD HKCU "${UNINSTKEY}" "NoRepair" 1
SectionEnd

Section "un.FRISTY AI (program files)" UnSecMain
  SectionIn RO
  nsExec::Exec 'taskkill /IM "${EXENAME}" /T /F'
  Sleep 800
  RMDir /r "$INSTDIR\resources"
  RMDir /r "$INSTDIR\locales"
  Delete "$INSTDIR\*.*"
  RMDir "$INSTDIR"
  Delete "$DESKTOP\${APPNAME}.lnk"
  RMDir /r "$SMPROGRAMS\${APPNAME}"
  DeleteRegKey HKCU "${UNINSTKEY}"
  ; "Start with Windows" entry written by Electron's setLoginItemSettings.
  DeleteRegValue HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "${APPUSERMODELID}"
  DeleteRegValue HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "${APPNAME}"
SectionEnd

Section /o "un.Personal data (settings, memory, conversations, downloaded speech models)" UnSecData
  RMDir /r "$APPDATA\${APPNAME}"
SectionEnd
