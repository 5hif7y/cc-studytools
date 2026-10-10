#include "config.h"

static void InitINIPath(void) {
    GetModuleFileNameW(NULL, g_iniPath, MAX_PATH);
    wchar_t* dot = wcsrchr(g_iniPath, L'.');
    if (dot) wcscpy(dot, L".ini");
    else     wcscat(g_iniPath, L".ini");
}

static void SaveConfig(void) {
    /* Guardar path del exe */
    WritePrivateProfileStringW(L"General", L"ExePath", g_exePath, g_iniPath);
    
    /* Guardar pestaña activa */
    int tab = (int)SendMessageW(g_hTab, TCM_GETCURSEL, 0, 0);
    wchar_t tabStr[16];
    swprintf(tabStr, 16, L"%d", tab);
    WritePrivateProfileStringW(L"General", L"ActiveTab", tabStr, g_iniPath);
    
    /* Offline - Mapa y GameInfo */
    wchar_t mapName[128] = L"", gameInfo[128] = L"";
    GetDlgItemTextW(g_hPageOffline, ID_COMBO_MAP, mapName, 128);
    GetDlgItemTextW(g_hPageOffline, ID_COMBO_GAME, gameInfo, 128);
    WritePrivateProfileStringW(L"Offline", L"Map", mapName, g_iniPath);
    WritePrivateProfileStringW(L"Offline", L"GameInfo", gameInfo, g_iniPath);
    
    /* Offline - Opciones */
    WritePrivateProfileStringW(L"Offline", L"UpdateIniAuto", 
        IsDlgButtonChecked(g_hPageOffline, ID_CHK_UPDATE) == BST_CHECKED ? L"1" : L"0", g_iniPath);
    WritePrivateProfileStringW(L"Offline", L"SkipScript",
        IsDlgButtonChecked(g_hPageOffline, ID_CHK_SKIP) == BST_CHECKED ? L"1" : L"0", g_iniPath);
    WritePrivateProfileStringW(L"Offline", L"NoStartupMovies",
        IsDlgButtonChecked(g_hPageOffline, ID_CHK_NOMOVIES) == BST_CHECKED ? L"1" : L"0", g_iniPath);
    WritePrivateProfileStringW(L"Offline", L"NoSplash",
        IsDlgButtonChecked(g_hPageOffline, ID_CHK_NOSPLASH) == BST_CHECKED ? L"1" : L"0", g_iniPath);
    WritePrivateProfileStringW(L"Offline", L"PlayersReady",
        IsDlgButtonChecked(g_hPageOffline, ID_CHK_READY) == BST_CHECKED ? L"1" : L"0", g_iniPath);
    WritePrivateProfileStringW(L"Offline", L"Listen",
        IsDlgButtonChecked(g_hPageOffline, ID_CHK_LISTEN) == BST_CHECKED ? L"1" : L"0", g_iniPath);
    
    /* Offline - Parámetros numéricos */
    wchar_t val[32];
    swprintf(val, 32, L"%d", GetDlgItemInt(g_hPageOffline, ID_EDIT_MINPLAY, NULL, FALSE));
    WritePrivateProfileStringW(L"Offline", L"MinNetPlayers", val, g_iniPath);
    
    swprintf(val, 32, L"%d", GetDlgItemInt(g_hPageOffline, ID_EDIT_GOAL, NULL, TRUE));
    WritePrivateProfileStringW(L"Offline", L"GoalScore", val, g_iniPath);
    
    swprintf(val, 32, L"%d", GetDlgItemInt(g_hPageOffline, ID_EDIT_WARMUP, NULL, TRUE));
    WritePrivateProfileStringW(L"Offline", L"WarmupTime", val, g_iniPath);
    
    swprintf(val, 32, L"%d", GetDlgItemInt(g_hPageOffline, ID_EDIT_TIMELIM, NULL, TRUE));
    WritePrivateProfileStringW(L"Offline", L"TimeLimit", val, g_iniPath);
    
    /* Online - Configuración */
    wchar_t address[64] = L"", port[16] = L"", lang[16] = L"";
    GetDlgItemTextW(g_hPageOnline, ID_EDIT_ADDRESS, address, 64);
    GetDlgItemTextW(g_hPageOnline, ID_EDIT_PORT, port, 16);
    GetDlgItemTextW(g_hPageOnline, ID_COMBO_LANG, lang, 16);
    
    WritePrivateProfileStringW(L"Online", L"Address", address, g_iniPath);
    WritePrivateProfileStringW(L"Online", L"Port", port, g_iniPath);
    WritePrivateProfileStringW(L"Online", L"Lang", lang, g_iniPath);
    WritePrivateProfileStringW(L"Online", L"OverrideAddress",
        IsDlgButtonChecked(g_hPageOnline, ID_CHK_OVERRIDE) == BST_CHECKED ? L"1" : L"0", g_iniPath);
    WritePrivateProfileStringW(L"Online", L"NoStartupMovies",
        IsDlgButtonChecked(g_hPageOnline, ID_CHK_ON_NOMOV) == BST_CHECKED ? L"1" : L"0", g_iniPath);
    WritePrivateProfileStringW(L"Online", L"NoSplash",
        IsDlgButtonChecked(g_hPageOnline, ID_CHK_ON_NOSPL) == BST_CHECKED ? L"1" : L"0", g_iniPath);
}

static void LoadConfig(void) {
    /* Cargar path del exe */
    wchar_t temp[MAX_PATH];
    if (GetPrivateProfileStringW(L"General", L"ExePath", L"", temp, MAX_PATH, g_iniPath) > 0) {
        wcsncpy(g_exePath, temp, MAX_PATH);
        SetDlgItemTextW(FindWindowW(L"CCLauncher", NULL), ID_EDIT_EXE, g_exePath);
    }
    
    /* Cargar pestaña activa */
    if (GetPrivateProfileStringW(L"General", L"ActiveTab", L"0", temp, 16, g_iniPath) > 0) {
        int tab = _wtoi(temp);
        SendMessageW(g_hTab, TCM_SETCURSEL, tab, 0);
        SwitchTab(tab);
    }
    
    /* Offline - Mapa y GameInfo */
    GetPrivateProfileStringW(L"Offline", L"Map", L"midtown", temp, 128, g_iniPath);
    HWND hComboMap = GetDlgItem(g_hPageOffline, ID_COMBO_MAP);
    SendMessageW(hComboMap, CB_SELECTSTRING, 0, (LPARAM)temp);
    
    GetPrivateProfileStringW(L"Offline", L"GameInfo", L"CrimeCraft.LobbyGameInfo", temp, 128, g_iniPath);
    HWND hComboGame = GetDlgItem(g_hPageOffline, ID_COMBO_GAME);
    SendMessageW(hComboGame, CB_SELECTSTRING, 0, (LPARAM)temp);
    
    /* Offline - Opciones */
    CheckDlgButton(g_hPageOffline, ID_CHK_UPDATE,
        GetPrivateProfileStringW(L"Offline", L"UpdateIniAuto", L"0", temp, 16, g_iniPath)[0] == L'1' ? BST_CHECKED : BST_UNCHECKED);
    CheckDlgButton(g_hPageOffline, ID_CHK_SKIP,
        GetPrivateProfileStringW(L"Offline", L"SkipScript", L"0", temp, 16, g_iniPath)[0] == L'1' ? BST_CHECKED : BST_UNCHECKED);
    CheckDlgButton(g_hPageOffline, ID_CHK_NOMOVIES,
        GetPrivateProfileStringW(L"Offline", L"NoStartupMovies", L"1", temp, 16, g_iniPath)[0] == L'1' ? BST_CHECKED : BST_UNCHECKED);
    CheckDlgButton(g_hPageOffline, ID_CHK_NOSPLASH,
        GetPrivateProfileStringW(L"Offline", L"NoSplash", L"1", temp, 16, g_iniPath)[0] == L'1' ? BST_CHECKED : BST_UNCHECKED);
    CheckDlgButton(g_hPageOffline, ID_CHK_READY,
        GetPrivateProfileStringW(L"Offline", L"PlayersReady", L"1", temp, 16, g_iniPath)[0] == L'1' ? BST_CHECKED : BST_UNCHECKED);
    CheckDlgButton(g_hPageOffline, ID_CHK_LISTEN,
        GetPrivateProfileStringW(L"Offline", L"Listen", L"1", temp, 16, g_iniPath)[0] == L'1' ? BST_CHECKED : BST_UNCHECKED);
    
    /* Offline - Parámetros numéricos */
    GetPrivateProfileStringW(L"Offline", L"MinNetPlayers", L"1", temp, 32, g_iniPath);
    SetDlgItemTextW(g_hPageOffline, ID_EDIT_MINPLAY, temp);
    
    GetPrivateProfileStringW(L"Offline", L"GoalScore", L"25", temp, 32, g_iniPath);
    SetDlgItemTextW(g_hPageOffline, ID_EDIT_GOAL, temp);
    
    GetPrivateProfileStringW(L"Offline", L"WarmupTime", L"0", temp, 32, g_iniPath);
    SetDlgItemTextW(g_hPageOffline, ID_EDIT_WARMUP, temp);
    
    GetPrivateProfileStringW(L"Offline", L"TimeLimit", L"30", temp, 32, g_iniPath);
    SetDlgItemTextW(g_hPageOffline, ID_EDIT_TIMELIM, temp);
    
    /* Online - Configuración */
    GetPrivateProfileStringW(L"Online", L"Address", L"213.165.42.41", temp, 64, g_iniPath);
    SetDlgItemTextW(g_hPageOnline, ID_EDIT_ADDRESS, temp);
    
    GetPrivateProfileStringW(L"Online", L"Port", L"5555", temp, 16, g_iniPath);
    SetDlgItemTextW(g_hPageOnline, ID_EDIT_PORT, temp);
    
    GetPrivateProfileStringW(L"Online", L"Lang", L"INT", temp, 16, g_iniPath);
    HWND hLang = GetDlgItem(g_hPageOnline, ID_COMBO_LANG);
    SendMessageW(hLang, CB_SELECTSTRING, 0, (LPARAM)temp);
    
    CheckDlgButton(g_hPageOnline, ID_CHK_OVERRIDE,
        GetPrivateProfileStringW(L"Online", L"OverrideAddress", L"0", temp, 16, g_iniPath)[0] == L'1' ? BST_CHECKED : BST_UNCHECKED);
    CheckDlgButton(g_hPageOnline, ID_CHK_ON_NOMOV,
        GetPrivateProfileStringW(L"Online", L"NoStartupMovies", L"1", temp, 16, g_iniPath)[0] == L'1' ? BST_CHECKED : BST_UNCHECKED);
    CheckDlgButton(g_hPageOnline, ID_CHK_ON_NOSPL,
        GetPrivateProfileStringW(L"Online", L"NoSplash", L"1", temp, 16, g_iniPath)[0] == L'1' ? BST_CHECKED : BST_UNCHECKED);
}
