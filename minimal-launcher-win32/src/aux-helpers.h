/* ============================================================
   Helpers de UI
   ============================================================ */
static HWND CreateGroupBox(HWND parent, const wchar_t* text,
                           int x, int y, int w, int h);

static HWND CreateLabel(HWND parent, const wchar_t* text,
                           int x, int y, int w, int h);

static HWND CreateEdit(HWND parent, int id, const wchar_t* def,
                           int x, int y, int w, int h);

static HWND CreateCheck(HWND parent, int id, const wchar_t* text,
                           int x, int y, int w, int h);

static HWND CreateButton(HWND parent, int id, const wchar_t* text,
                           int x, int y, int w, int h);

static HWND CreateCombo(HWND parent, int id, int x, int y, int w, int h);

/* ============================================================
   SHA1 - Cálculo y comparación
   ============================================================ */
static void BinToHex(const BYTE* bin, int len, wchar_t* out);

static BOOL CalcFileSHA1(const wchar_t* filePath, wchar_t* outHex);

typedef enum {
    VER_UNKNOWN = 0,
    VER_UNPATCHED,
    VER_PATCHED
} VerStatus;

typedef struct {
    VerStatus      status;
    const wchar_t* version;
} VerResult;

static VerResult CheckVersion(const wchar_t* sha1Hex);

/* ============================================================
   Diálogo de selección de archivo
   ============================================================ */
static BOOL BrowseForExe(HWND owner, wchar_t* outPath, int outSize);

/* ============================================================
   Actualizar estado con colores (SIN LEAK)
   ============================================================ */
static void UpdateVersionStatus(void);


