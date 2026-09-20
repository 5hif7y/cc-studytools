/* ============================================================
   Helpers de UI
   ============================================================ */
static HWND CreateGroupBox(HWND parent, const wchar_t* text,
                           int x, int y, int w, int h) {
    return CreateWindowExW(0, L"BUTTON", text,
        WS_CHILD | WS_VISIBLE | BS_GROUPBOX, x, y, w, h,
        parent, NULL, g_hInst, NULL);
}

static HWND CreateLabel(HWND parent, const wchar_t* text,
                        int x, int y, int w, int h) {
    return CreateWindowExW(0, L"STATIC", text,
        WS_CHILD | WS_VISIBLE | SS_LEFT, x, y, w, h,
        parent, NULL, g_hInst, NULL);
}

static HWND CreateEdit(HWND parent, int id, const wchar_t* def,
                       int x, int y, int w, int h) {
    return CreateWindowExW(WS_EX_CLIENTEDGE, L"EDIT", def,
        WS_CHILD | WS_VISIBLE | ES_AUTOHSCROLL, x, y, w, h,
        parent, (HMENU)(intptr_t)id, g_hInst, NULL);
}

static HWND CreateCheck(HWND parent, int id, const wchar_t* text,
                        int x, int y, int w, int h) {
    return CreateWindowExW(0, L"BUTTON", text,
        WS_CHILD | WS_VISIBLE | BS_AUTOCHECKBOX, x, y, w, h,
        parent, (HMENU)(intptr_t)id, g_hInst, NULL);
}

static HWND CreateButton(HWND parent, int id, const wchar_t* text,
                         int x, int y, int w, int h) {
    return CreateWindowExW(0, L"BUTTON", text,
        WS_CHILD | WS_VISIBLE | BS_PUSHBUTTON, x, y, w, h,
        parent, (HMENU)(intptr_t)id, g_hInst, NULL);
}

static HWND CreateCombo(HWND parent, int id, int x, int y, int w, int h) {
    return CreateWindowExW(0, L"COMBOBOX", L"",
        WS_CHILD | WS_VISIBLE | CBS_DROPDOWNLIST | WS_VSCROLL,
        x, y, w, h, parent, (HMENU)(intptr_t)id, g_hInst, NULL);
}

/* ============================================================
   SHA1 - Cálculo y comparación
   ============================================================ */
static void BinToHex(const BYTE* bin, int len, wchar_t* out) {
    static const wchar_t hex[] = L"0123456789abcdef";
    for (int i = 0; i < len; i++) {
        out[i * 2]     = hex[(bin[i] >> 4) & 0x0F];
        out[i * 2 + 1] = hex[ bin[i]       & 0x0F];
    }
    out[len * 2] = L'\0';
}

static BOOL CalcFileSHA1(const wchar_t* filePath, wchar_t* outHex) {
    HANDLE hFile = CreateFileW(filePath, GENERIC_READ, FILE_SHARE_READ,
                               NULL, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, NULL);
    if (hFile == INVALID_HANDLE_VALUE) return FALSE;

    HCRYPTPROV hProv = 0;
    HCRYPTHASH hHash = 0;
    BOOL ok = FALSE;

    if (!CryptAcquireContextW(&hProv, NULL, NULL, PROV_RSA_FULL,
                              CRYPT_VERIFYCONTEXT))
        goto cleanup;
    if (!CryptCreateHash(hProv, CALG_SHA1, 0, 0, &hHash))
        goto cleanup;

    BYTE buf[65536];
    DWORD bytesRead;
    while (ReadFile(hFile, buf, sizeof(buf), &bytesRead, NULL) && bytesRead > 0) {
        if (!CryptHashData(hHash, buf, bytesRead, 0))
            goto cleanup;
    }

    BYTE hashBin[20];
    DWORD hashLen = sizeof(hashBin);
    if (!CryptGetHashParam(hHash, HP_HASHVAL, hashBin, &hashLen, 0))
        goto cleanup;

    BinToHex(hashBin, 20, outHex);
    ok = TRUE;

cleanup:
    if (hHash) CryptDestroyHash(hHash);
    if (hProv) CryptReleaseContext(hProv, 0);
    CloseHandle(hFile);
    return ok;
}

typedef enum {
    VER_UNKNOWN = 0,
    VER_UNPATCHED,
    VER_PATCHED
} VerStatus;

typedef struct {
    VerStatus      status;
    const wchar_t* version;
} VerResult;

static VerResult CheckVersion(const wchar_t* sha1Hex) {
    VerResult res = { VER_UNKNOWN, NULL };
    for (int i = 0; KNOWN_VERSIONS[i].sha1; i++) {
        if (_wcsicmp(sha1Hex, KNOWN_VERSIONS[i].sha1) == 0) {
            res.status  = KNOWN_VERSIONS[i].patched ? VER_PATCHED : VER_UNPATCHED;
            res.version = KNOWN_VERSIONS[i].version;
            return res;
        }
    }
    return res;
}

/* ============================================================
   Diálogo de selección de archivo
   ============================================================ */
static BOOL BrowseForExe(HWND owner, wchar_t* outPath, int outSize) {
    OPENFILENAMEW ofn = {0};
    wchar_t fileName[MAX_PATH] = L"CrimeCraft.exe";

    ofn.lStructSize     = sizeof(ofn);
    ofn.hwndOwner       = owner;
    ofn.lpstrFilter     = L"Executables\0*.exe\0Todos los archivos\0*.*\0";
    ofn.lpstrFile       = fileName;
    ofn.nMaxFile        = MAX_PATH;
    ofn.lpstrTitle      = L"Seleccionar CrimeCraft.exe";
    ofn.Flags           = OFN_FILEMUSTEXIST | OFN_PATHMUSTEXIST |
                          OFN_HIDEREADONLY | OFN_EXPLORER;
    ofn.lpstrDefExt     = L"exe";

    if (GetOpenFileNameW(&ofn)) {
        wcsncpy(outPath, fileName, outSize - 1);
        outPath[outSize - 1] = L'\0';
        return TRUE;
    }
    return FALSE;
}

/* ============================================================
   Actualizar estado con colores (SIN LEAK)
   ============================================================ */
static void UpdateVersionStatus(void) {
    if (!g_hLabelStatus || g_exePath[0] == L'\0') {
        if (g_hLabelStatus) {
            SetWindowTextW(g_hLabelStatus, L"Estado: Sin ejecutable seleccionado");
            g_statusColor = 0;
            RedrawWindow(g_hLabelStatus, NULL, NULL,
                RDW_INVALIDATE | RDW_UPDATENOW | RDW_ERASE);
        }
        return;
    }

    wchar_t sha1[41];
    if (!CalcFileSHA1(g_exePath, sha1)) {
        SetWindowTextW(g_hLabelStatus,
            L"Estado: \u26A0 Error al calcular SHA1 (archivo no accesible)");
        g_statusColor = 3;
        RedrawWindow(g_hLabelStatus, NULL, NULL,
            RDW_INVALIDATE | RDW_UPDATENOW | RDW_ERASE);
        return;
    }

    VerResult vr = CheckVersion(sha1);
    wchar_t msg[256];

    switch (vr.status) {
    case VER_UNPATCHED:
        swprintf(msg, 256,
            L"Estado: \u2705 UNPATCHED - Version %s  |  SHA1: %s",
            vr.version, sha1);
        g_statusColor = 2;
        break;
    case VER_PATCHED:
        swprintf(msg, 256,
            L"Estado: \u2699 PATCHED - Version %s  |  SHA1: %s",
            vr.version, sha1);
        g_statusColor = 1;
        break;
    default:
        swprintf(msg, 256,
            L"Estado: \u274C UNSUPPORTED VERSION  |  SHA1: %s",
            sha1);
        g_statusColor = 3;
        break;
    }

    SetWindowTextW(g_hLabelStatus, msg);
    RedrawWindow(g_hLabelStatus, NULL, NULL,
        RDW_INVALIDATE | RDW_UPDATENOW | RDW_ERASE);
}
