/*
 * CrimeCraft GangWars - Launcher Win32 (Unicode + SHA1 + Config INI)
 * Compilar con MinGW:
 *   gcc src/launcher.c -o launcher.exe -lcomctl32 -lshell32 -ladvapi32 -mwindows -DUNICODE -D_UNICODE
 * Compilar con MSVC:
 *   cl src/launcher.c /Fe:launcher.exe comctl32.lib shell32.lib advapi32.lib /link /SUBSYSTEM:WINDOWS /DUNICODE /D_UNICODE
 */

#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <commctrl.h>
#include <shlobj.h>
#include <commdlg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <shellapi.h>
#include <wincrypt.h>

#ifdef _MSC_VER
#pragma comment(lib, "comctl32.lib")
#pragma comment(lib, "shell32.lib")
#pragma comment(lib, "advapi32.lib")
#pragma comment(linker, "\"/manifestdependency:type='win32' \
    name='Microsoft.Windows.Common-Controls' version='6.0.0.0' \
    processorArchitecture='*' publicKeyToken='6595b64144ccf1df' language='*'\"")
#endif

/* ============================================================
   IDs de controles
   ============================================================ */
#define ID_EDIT_EXE       1000
#define ID_BTN_BROWSE     1001
#define ID_TAB_MAIN       1002
#define ID_BTN_LAUNCH     1003
#define ID_LABEL_STATUS   1004

#define ID_COMBO_MAP      2000
#define ID_COMBO_GAME     2001
#define ID_CHK_UPDATE     2010
#define ID_CHK_SKIP       2011
#define ID_CHK_NOMOVIES   2012
#define ID_CHK_NOSPLASH   2013
#define ID_EDIT_MINPLAY   2020
#define ID_EDIT_GOAL      2021
#define ID_EDIT_WARMUP    2022
#define ID_EDIT_TIMELIM   2023
#define ID_CHK_READY      2030
#define ID_CHK_LISTEN     2031

#define ID_CHK_OVERRIDE   3000
#define ID_EDIT_ADDRESS   3001
#define ID_EDIT_PORT      3002
#define ID_COMBO_LANG     3003
#define ID_CHK_ON_NOMOV   3010
#define ID_CHK_ON_NOSPL   3011

/* ============================================================
   Configuración INI
   ============================================================ */
static wchar_t g_iniPath[MAX_PATH] = L"";

static void InitINIPath(void);

static void SaveConfig(void);
static void LoadConfig(void);


/* ============================================================
   Estructura de versión conocida
   ============================================================ */
typedef struct {
    const wchar_t* sha1;
    const wchar_t* version;
    int            patched;
} KnownVersion;

static const KnownVersion KNOWN_VERSIONS[] = {
    { L"629ee582745f7e0715a1a1586876ffd1e4f7ddae", L"0.25.06.91089", 0 },
    { L"3100744917a87c9c0d06022eec616c7c51a6dbcc", L"0.25.06.91089-HackShield patch", 1 },
    { NULL, NULL, 0 }
};



/* ============================================================
   Estado global
   ============================================================ */
static wchar_t g_exePath[MAX_PATH] = L"";
static HINSTANCE g_hInst = NULL;
static HWND g_hTab = NULL;
static HWND g_hPageOffline = NULL;
static HWND g_hPageOnline = NULL;
static HWND g_hLabelStatus = NULL;
static int g_statusColor = 0;
static HBRUSH g_hStatusBrush = NULL;  /* Brush reutilizable - SIN LEAK */
static HFONT g_hFontStatus = NULL;
static HFONT g_hFontLaunch = NULL;



/* ============================================================
   Página Online
   ============================================================ */
static void BuildOnlinePage(HWND parent) {
    const int MARGIN_X = 15;
    const int ROW_H    = 24;
    const int GAP      = 6;

    int y = 10;

    const int Y_GRP_SRV   = y;
    const int H_GRP_SRV   = 130;
    CreateGroupBox(parent, L"Configuracion del servidor",
                   MARGIN_X, Y_GRP_SRV, 720, H_GRP_SRV);
    int cy = Y_GRP_SRV + 20;

    CreateCheck(parent, ID_CHK_OVERRIDE, L"-OVERRIDEYAKAADDRESS",
                MARGIN_X + 10, cy, 200, 20);
    cy += ROW_H + GAP;

    CreateLabel(parent, L"-YAKAADDRESS:", MARGIN_X + 10, cy, 110, 20);
    CreateEdit(parent, ID_EDIT_ADDRESS, L"213.165.42.41",
               MARGIN_X + 120, cy, 170, 22);

    CreateLabel(parent, L"-LANG:", MARGIN_X + 320, cy, 60, 20);
    HWND hLang = CreateCombo(parent, ID_COMBO_LANG,
                          MARGIN_X + 380, cy, 130, 200);
    for (int i = 0; LANGS[i]; i++)
        SendMessageW(hLang, CB_ADDSTRING, 0, (LPARAM)LANGS[i]);
    SendMessageW(hLang, CB_SETCURSEL, 0, 0);
    cy += ROW_H + GAP;

    CreateLabel(parent, L"-YAKAPORT:", MARGIN_X + 10, cy, 110, 20);
    CreateEdit(parent, ID_EDIT_PORT, L"5555",
               MARGIN_X + 120, cy, 110, 22);
    cy += ROW_H + GAP;

    const int Y_GRP_CLI   = Y_GRP_SRV + H_GRP_SRV + 10;
    const int H_GRP_CLI   = 55;
    CreateGroupBox(parent, L"Opciones de cliente",
                   MARGIN_X, Y_GRP_CLI, 720, H_GRP_CLI);
    cy = Y_GRP_CLI + 20;
    CreateCheck(parent, ID_CHK_ON_NOMOV, L"-nostartupmovies",
                MARGIN_X + 10, cy, 140, 20);
    CreateCheck(parent, ID_CHK_ON_NOSPL, L"-nosplash",
                MARGIN_X + 160, cy, 100, 20);

    CheckDlgButton(parent, ID_CHK_ON_NOMOV, BST_CHECKED);
    CheckDlgButton(parent, ID_CHK_ON_NOSPL, BST_CHECKED);
}

/* ============================================================
   Página Offline
   ============================================================ */
static void BuildOfflinePage(HWND parent) {
    const int MARGIN_X = 15;
    const int ROW_H    = 24;
    const int GAP      = 6;

    int y = 10;

    const int Y_GRP_MAP   = y;
    const int H_GRP_MAP   = 75;
    CreateGroupBox(parent, L"Mapa y modo de juego",
                   MARGIN_X, Y_GRP_MAP, 720, H_GRP_MAP);
    int cy = Y_GRP_MAP + 20;

    CreateLabel(parent, L"Mapa:", MARGIN_X + 10, cy, 60, 20);
    HWND hComboMap = CreateCombo(parent, ID_COMBO_MAP,
                              MARGIN_X + 75, cy, 260, 200);
    for (int i = 0; MAPS[i]; i++)
        SendMessageW(hComboMap, CB_ADDSTRING, 0, (LPARAM)MAPS[i]);
    SendMessageW(hComboMap, CB_SETCURSEL, 0, 0);

    CreateLabel(parent, L"GameInfo:", MARGIN_X + 350, cy, 75, 20);
    HWND hComboGame = CreateCombo(parent, ID_COMBO_GAME,
                               MARGIN_X + 430, cy, 275, 200);
    for (int i = 0; GAME_MODES[i]; i++)
        SendMessageW(hComboGame, CB_ADDSTRING, 0, (LPARAM)GAME_MODES[i]);
    SendMessageW(hComboGame, CB_SETCURSEL, 0, 0);

    const int Y_GRP_OPT   = Y_GRP_MAP + H_GRP_MAP + 10;
    const int H_GRP_OPT   = 50;
    CreateGroupBox(parent, L"Opciones de juego",
                   MARGIN_X, Y_GRP_OPT, 720, H_GRP_OPT);
    cy = Y_GRP_OPT + 18;
    int cx = MARGIN_X + 10;
    CreateCheck(parent, ID_CHK_UPDATE,   L"-updateinisauto",         cx, cy, 140, 20); cx += 145;
    CreateCheck(parent, ID_CHK_SKIP,     L"-skipscriptoutdatedness", cx, cy, 175, 20); cx += 180;
    CreateCheck(parent, ID_CHK_NOMOVIES, L"-nostartupmovies",        cx, cy, 140, 20); cx += 145;
    CreateCheck(parent, ID_CHK_NOSPLASH, L"-nosplash",               cx, cy, 80,  20);

    const int Y_GRP_CONN  = Y_GRP_OPT + H_GRP_OPT + 10;
    const int H_GRP_CONN  = 110;
    CreateGroupBox(parent, L"Parametros de conexion",
                   MARGIN_X, Y_GRP_CONN, 720, H_GRP_CONN);
    cy = Y_GRP_CONN + 18;
    int col1 = MARGIN_X + 10;
    int col2 = MARGIN_X + 190;
    int col3 = MARGIN_X + 370;
    int col4 = MARGIN_X + 530;

    CreateLabel(parent, L"MinNetPlayers:", col1, cy, 100, 20);
    CreateEdit(parent, ID_EDIT_MINPLAY, L"1", col1 + 100, cy, 70, 22);

    CreateLabel(parent, L"GoalScore:", col2, cy, 80, 20);
    CreateEdit(parent, ID_EDIT_GOAL, L"25", col2 + 80, cy, 70, 22);

    CreateLabel(parent, L"WarmupTime:", col3, cy, 90, 20);
    CreateEdit(parent, ID_EDIT_WARMUP, L"0", col3 + 90, cy, 70, 22);

    CreateLabel(parent, L"TimeLimit:", col4, cy, 80, 20);
    CreateEdit(parent, ID_EDIT_TIMELIM, L"30", col4 + 75, cy, 70, 22);

    cy += ROW_H + GAP;
    CreateCheck(parent, ID_CHK_READY,  L"PlayersMustBeReady", col1, cy, 160, 20);
    CreateCheck(parent, ID_CHK_LISTEN, L"listen",             col2, cy, 80,  20);
}

/* ============================================================
   Manejo de pestañas
   ============================================================ */
static void SwitchTab(int index) {
    ShowWindow(g_hPageOnline,  index == 0 ? SW_SHOW : SW_HIDE);
    ShowWindow(g_hPageOffline, index == 1 ? SW_SHOW : SW_HIDE);
}

/* ============================================================
   Obtener directorio base del ejecutable
   ============================================================ */
static void GetExeDir(const wchar_t* exePath, wchar_t* outDir, int outSize) {
    wcsncpy(outDir, exePath, outSize - 1);
    outDir[outSize - 1] = L'\0';
    wchar_t* slash = wcsrchr(outDir, L'\\');
    if (slash) *slash = L'\0';
}


/* ============================================================
   WndProc principal
   ============================================================ */
LRESULT CALLBACK WndProc(HWND hWnd, UINT msg, WPARAM wp, LPARAM lp) {
    switch (msg) {
    case WM_CREATE: {
        CreateGroupBox(hWnd, L"Instalacion", 10, 10, 760, 50);
        CreateLabel(hWnd, L"CrimeCraft.exe:", 20, 25, 110, 20);
        CreateEdit(hWnd, ID_EDIT_EXE, g_exePath, 135, 25, 530, 22);
        CreateButton(hWnd, ID_BTN_BROWSE, L"...", 675, 25, 35, 22);

        g_hTab = CreateWindowExW(0, WC_TABCONTROLW, L"",
            WS_CHILD | WS_VISIBLE | TCS_TABS,
            10, 70, 760, 310, hWnd,
            (HMENU)(intptr_t)ID_TAB_MAIN, g_hInst, NULL);

        TCITEMW tie = {0};
        tie.mask = TCIF_TEXT;
        tie.pszText = L"Online";
        SendMessageW(g_hTab, TCM_INSERTITEMW, 0, (LPARAM)&tie);
        tie.pszText = L"Offline";
        SendMessageW(g_hTab, TCM_INSERTITEMW, 1, (LPARAM)&tie);

        RECT rc;
        GetClientRect(g_hTab, &rc);
        SendMessageW(g_hTab, TCM_ADJUSTRECT, FALSE, (LPARAM)&rc);
        rc.left  += 2;
        rc.right -= 2;
        rc.top   += 2;
        rc.bottom -= 2;

        int tabW = rc.right - rc.left;
        int tabH = rc.bottom - rc.top;

        g_hPageOnline = CreateWindowExW(0, L"STATIC", L"",
            WS_CHILD | WS_VISIBLE,
            rc.left, rc.top, tabW, tabH,
            g_hTab, NULL, g_hInst, NULL);
        BuildOnlinePage(g_hPageOnline);

        g_hPageOffline = CreateWindowExW(0, L"STATIC", L"",
            WS_CHILD,
            rc.left, rc.top, tabW, tabH,
            g_hTab, NULL, g_hInst, NULL);
        BuildOfflinePage(g_hPageOffline);

        ShowWindow(g_hPageOnline, SW_SHOW);
        ShowWindow(g_hPageOffline, SW_HIDE);

        g_hLabelStatus = CreateWindowExW(0, L"STATIC",
            L"Estado: Sin ejecutable seleccionado",
            WS_CHILD | WS_VISIBLE | SS_LEFT | SS_NOPREFIX,
            10, 390, 760, 22, hWnd,
            (HMENU)(intptr_t)ID_LABEL_STATUS, g_hInst, NULL);
        g_hFontStatus = CreateFontW(-12, 0, 0, 0, FW_BOLD, 0, 0, 0,
            DEFAULT_CHARSET, 0, 0, 0, 0, L"Segoe UI");
        SendMessageW(g_hLabelStatus, WM_SETFONT, (WPARAM)g_hFontStatus, TRUE);

        HWND hLaunch = CreateButton(hWnd, ID_BTN_LAUNCH,
            L"\u25B6  LAUNCH", 10, 420, 760, 40);
        g_hFontLaunch = CreateFontW(-14, 0, 0, 0, FW_BOLD, 0, 0, 0,
            DEFAULT_CHARSET, 0, 0, 0, 0, L"Segoe UI");
        SendMessageW(hLaunch, WM_SETFONT, (WPARAM)g_hFontLaunch, TRUE);

        /* Crear brush UNA SOLA VEZ */
        g_hStatusBrush = CreateSolidBrush(GetSysColor(COLOR_BTNFACE));

        if (g_exePath[0]) UpdateVersionStatus();
        
        /* Cargar configuración guardada */
        LoadConfig();

        return 0;
    }

    case WM_CTLCOLORSTATIC: {
        if ((HWND)lp == g_hLabelStatus) {
            HDC hdc = (HDC)wp;
            
            /* USAR BRUSH GLOBAL - SIN LEAK */
            SetBkColor(hdc, GetSysColor(COLOR_BTNFACE));
            
            switch (g_statusColor) {
            case 1:  SetTextColor(hdc, RGB(0, 128, 0)); break;
            case 2:  SetTextColor(hdc, RGB(200, 150, 0)); break;
            case 3:  SetTextColor(hdc, RGB(200, 0, 0)); break;
            default: SetTextColor(hdc, RGB(100, 100, 100)); break;
            }
            return (LRESULT)g_hStatusBrush;  /* Reutilizar, NO crear nuevo */
        }
        break;
    }

    case WM_COMMAND: {
        int id = LOWORD(wp);

        if (id == ID_BTN_BROWSE) {
            wchar_t newPath[MAX_PATH];
            if (BrowseForExe(hWnd, newPath, MAX_PATH)) {
                wcsncpy(g_exePath, newPath, MAX_PATH);
                SetDlgItemTextW(hWnd, ID_EDIT_EXE, g_exePath);
                UpdateVersionStatus();
                SaveConfig();  /* Guardar al cambiar */
            }
            return 0;
        }

        if (id == ID_BTN_LAUNCH) {
            if (g_exePath[0] == L'\0') {
                MessageBoxW(hWnd,
                    L"Selecciona el archivo CrimeCraft.exe primero.",
                    L"Error", MB_ICONWARNING);
                return 0;
            }

            wchar_t dir[MAX_PATH];
            GetExeDir(g_exePath, dir, MAX_PATH);
            if (dir[wcslen(dir)-1] != L'\\') wcscat(dir, L"\\");

            int tab = (int)SendMessageW(g_hTab, TCM_GETCURSEL, 0, 0);
            wchar_t cmd[2048];

            if (tab == 0) {
                /* MODO ONLINE */
                wchar_t address[64] = L"", port[16] = L"", lang[16] = L"";
                GetDlgItemTextW(g_hPageOnline, ID_EDIT_ADDRESS, address, 64);
                GetDlgItemTextW(g_hPageOnline, ID_EDIT_PORT,    port,    16);
                GetDlgItemTextW(g_hPageOnline, ID_COMBO_LANG,   lang,    16);

                BOOL overrideAddr = IsDlgButtonChecked(g_hPageOnline, ID_CHK_OVERRIDE) == BST_CHECKED;
                BOOL nomov = IsDlgButtonChecked(g_hPageOnline, ID_CHK_ON_NOMOV) == BST_CHECKED;
                BOOL nospl = IsDlgButtonChecked(g_hPageOnline, ID_CHK_ON_NOSPL) == BST_CHECKED;

                wchar_t opts[512] = L"";
                if (overrideAddr) wcscat(opts, L" -OVERRIDEYAKAADDRESS");
                if (address[0]) {
                    wchar_t tmp[128];
                    swprintf(tmp, 128, L" -YAKAADDRESS=%s", address);
                    wcscat(opts, tmp);
                }
                if (port[0]) {
                    wchar_t tmp[64];
                    swprintf(tmp, 64, L" -YAKAPORT=%s", port);
                    wcscat(opts, tmp);
                }
                if (lang[0]) {
                    wchar_t tmp[32];
                    swprintf(tmp, 32, L" -LANG=%s", lang);
                    wcscat(opts, tmp);
                }
                if (nomov) wcscat(opts, L" -nostartupmovies");
                if (nospl) wcscat(opts, L" -nosplash");

                swprintf(cmd, 2048,
                    L"/c start \"\" \"%s\"%s",
                    g_exePath, opts);

            } else {
                /* MODO OFFLINE */
                wchar_t mapName[128] = L"", gameInfo[128] = L"";
                GetDlgItemTextW(g_hPageOffline, ID_COMBO_MAP, mapName, 128);
                GetDlgItemTextW(g_hPageOffline, ID_COMBO_GAME, gameInfo, 128);

                int minPlay = GetDlgItemInt(g_hPageOffline, ID_EDIT_MINPLAY, NULL, FALSE);
                int goal    = GetDlgItemInt(g_hPageOffline, ID_EDIT_GOAL,    NULL, TRUE);
                int warmup  = GetDlgItemInt(g_hPageOffline, ID_EDIT_WARMUP,  NULL, TRUE);
                int timeLim = GetDlgItemInt(g_hPageOffline, ID_EDIT_TIMELIM, NULL, TRUE);

                BOOL upd   = IsDlgButtonChecked(g_hPageOffline, ID_CHK_UPDATE)   == BST_CHECKED;
                BOOL skip  = IsDlgButtonChecked(g_hPageOffline, ID_CHK_SKIP)     == BST_CHECKED;
                BOOL nomov = IsDlgButtonChecked(g_hPageOffline, ID_CHK_NOMOVIES) == BST_CHECKED;
                BOOL nospl = IsDlgButtonChecked(g_hPageOffline, ID_CHK_NOSPLASH) == BST_CHECKED;
                BOOL ready = IsDlgButtonChecked(g_hPageOffline, ID_CHK_READY)    == BST_CHECKED;
                BOOL listen= IsDlgButtonChecked(g_hPageOffline, ID_CHK_LISTEN)   == BST_CHECKED;

                wchar_t conn[512];
                swprintf(conn, 512,
                    L"MinNetPlayers=%d?GoalScore=%d?WarmupTime=%d?TimeLimit=%d"
                    L"?PlayersMustBeReady=%s%s",
                    minPlay, goal, warmup, timeLim,
                    ready ? L"true" : L"false",
                    listen ? L"?listen" : L"");

                wchar_t opts[256] = L"";
                if (upd)   wcscat(opts, L" -updateinisauto");
                if (skip)  wcscat(opts, L" -skipscriptoutdatedness");
                if (nomov) wcscat(opts, L" -nostartupmovies");
                if (nospl) wcscat(opts, L" -nosplash");

                swprintf(cmd, 2048,
                    L"/c start \"\" \"%s\" "
                    L"%s?game=%s?%s%s",
                    g_exePath, mapName, gameInfo, conn, opts);
            }

            ShellExecuteW(hWnd, L"open", L"cmd.exe", cmd, dir, SW_HIDE);
            return 0;
        }
        break;
    }

    case WM_NOTIFY: {
        LPNMHDR nmh = (LPNMHDR)lp;
        if (nmh->idFrom == ID_TAB_MAIN && nmh->code == TCN_SELCHANGE) {
            int tab = (int)SendMessageW(g_hTab, TCM_GETCURSEL, 0, 0);
            SwitchTab(tab);
            SaveConfig();  /* Guardar al cambiar pestaña */
            return 0;
        }
        break;
    }

    case WM_DESTROY: {
        /* LIMPIEZA - SIN LEAKS */
        if (g_hStatusBrush) DeleteObject(g_hStatusBrush);
        if (g_hFontStatus)  DeleteObject(g_hFontStatus);
        if (g_hFontLaunch)  DeleteObject(g_hFontLaunch);
        
        SaveConfig();  /* Guardar configuración al cerrar */
        PostQuitMessage(0);
        return 0;
    }
    }
    return DefWindowProcW(hWnd, msg, wp, lp);
}

/* ============================================================
   Entry point
   ============================================================ */
int WINAPI wWinMain(HINSTANCE hInst, HINSTANCE hPrev, LPWSTR cmdLine, int nShow) {
    g_hInst = hInst;
    InitCommonControls();
    InitINIPath();  /* Inicializar path del INI */

    if (cmdLine && cmdLine[0]) {
        const wchar_t* p = cmdLine;
        if (*p == L'"') p++;
        wcsncpy(g_exePath, p, MAX_PATH - 1);
        g_exePath[MAX_PATH - 1] = L'\0';
        wchar_t* end = wcschr(g_exePath, L'"');
        if (end) *end = L'\0';
    }

    WNDCLASSEXW wc = {0};
    wc.cbSize        = sizeof(wc);
    wc.style         = CS_HREDRAW | CS_VREDRAW;
    wc.lpfnWndProc   = WndProc;
    wc.hInstance     = hInst;
    wc.hCursor       = LoadCursor(NULL, IDC_ARROW);
    wc.hbrBackground = (HBRUSH)(COLOR_BTNFACE + 1);
    wc.lpszClassName = L"CCLauncher";
    wc.hIcon         = LoadIcon(NULL, IDI_APPLICATION);
    RegisterClassExW(&wc);

    HWND hWnd = CreateWindowExW(0, L"CCLauncher",
        L"CrimeCraft GangWars - Launcher",
        WS_OVERLAPPED | WS_CAPTION | WS_SYSMENU | WS_MINIMIZEBOX,
        CW_USEDEFAULT, CW_USEDEFAULT, 800, 510,
        NULL, NULL, hInst, NULL);

    if (!hWnd) return 1;
    ShowWindow(hWnd, nShow);
    UpdateWindow(hWnd);

    MSG msg;
    while (GetMessageW(&msg, NULL, 0, 0)) {
        TranslateMessage(&msg);
        DispatchMessageW(&msg);
    }
    return (int)msg.wParam;
}
