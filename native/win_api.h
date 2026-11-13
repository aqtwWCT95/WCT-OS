#ifndef WCT_WIN_API_H
#define WCT_WIN_API_H

/* 脚本窗口：预分配 N 个虚拟 type_id，避免污染 g_apps[] 桌面图标 */
#define SCRIPTWIN_BASE  1000
#define SCRIPTWIN_N     8
#define SW_ITEMS        64
#define SW_TEXT_LEN     128
#define SW_TITLE_LEN    64
#define SW_LABEL_LEN    64

/* 前向声明：win_open / win_close 在 gui.inc 后面定义 */
static int  win_open(int type);
static void win_close(int i);

typedef struct {
    int kind;              /* 0=rect 1=text 2=border 3=button */
    int x, y, w, h;
    UINT32 color;
    int ctrl_id;
    CHAR16 text[SW_TEXT_LEN];              /* ★ 恢复：这是控件文字 */
} SwItem;

typedef struct {
    int alive;
    int w, h;
    CHAR16 title_zh[SW_TITLE_LEN];
    CHAR16 title_en[SW_TITLE_LEN];
    SwItem items[SW_ITEMS];
    int item_count;
    CHAR16 click_label[SW_ITEMS][SW_LABEL_LEN];   /* ★ 修：二维，每个 ctrl_id 一个回调标签 */
    CHAR16 click_label_generic[SW_LABEL_LEN];
    CHAR16 close_label[SW_LABEL_LEN];
    CHAR16 key_label[SW_LABEL_LEN];
} ScriptWin;

static ScriptWin s_wins[SCRIPTWIN_N];
static int       s_in_close = 0;

/* 脚本缓存：run_label 扫描它来找 :label */
static char s_script_cache[8192];
static int  s_script_len = 0;
static int  s_call_depth = 0;

static void win_api_load_script(const char *t, int n) {
    if (n >= (int)sizeof(s_script_cache) - 1) n = sizeof(s_script_cache) - 2;
    for (int i = 0; i < n; ++i) s_script_cache[i] = t[i];
    s_script_cache[n] = 0;
    s_script_len = n;
}

static void win_api_unload_script(void) {
    s_script_len = 0;
    s_script_cache[0] = 0;
}

static void sw_copy16(CHAR16 *dst, int cap, const char *src) {
    int i = 0; if (cap <= 0) return;
    while (src[i] && i + 1 < cap) { dst[i] = (CHAR16)(unsigned char)src[i]; ++i; }
    dst[i] = 0;
}

static UINT32 sw_parse_color(const char *s) {
    UINT32 v = 0; int n = 0;
    while (*s && n < 6) {
        char c = *s; int d;
        if      (c >= '0' && c <= '9') d = c - '0';
        else if (c >= 'a' && c <= 'f') d = c - 'a' + 10;
        else if (c >= 'A' && c <= 'F') d = c - 'A' + 10;
        else break;
        v = v * 16 + d; ++s; ++n;
    }
    return gfx_rgb((v >> 16) & 0xFF, (v >> 8) & 0xFF, v & 0xFF);
}

/* ---------- 窗口回调 ---------- */
static void run_label(const CHAR16 *label);

static void sw_draw(GuiWin *w) {
    int slot = w->type - SCRIPTWIN_BASE;
    if (slot < 0 || slot >= SCRIPTWIN_N) return;
    ScriptWin *sw = &s_wins[slot];
    for (int i = 0; i < sw->item_count; ++i) {
        SwItem *it = &sw->items[i];
        int px = w->x + it->x;
        int py = w->y + it->y + 30;                 /* 30 = 标题栏高度 */
        if (it->kind == 0)      gfx_fill(px, py, it->w, it->h, it->color);
        else if (it->kind == 1) gfx_text_w(px, py, it->text, it->color);
        else if (it->kind == 2) gfx_border(px, py, it->w, it->h, it->color);
        else if (it->kind == 3) {
            int hot = ui_hit(px, py, it->w, it->h);
            gfx_fill(px, py, it->w, it->h, hot ? gfx_top : gfx_panel);
            gfx_border(px, py, it->w, it->h, gfx_accent);
            gfx_text_w(px + (it->w - (int)wlen(it->text) * 8) / 2,
                       py + (it->h - 16) / 2, it->text, gfx_text_c);
        }
    }
}

static void fire_event(const CHAR16 *s) {
    if (!s || !s[0]) return;
    if (s[0] == L':') { run_label(s + 1); return; }
    CHAR16 buf[256]; int i = 0;
    while (s[i] && i < 255) { buf[i] = s[i]; ++i; }
    buf[i] = 0;
    process_command(buf);
}

static void sw_click(GuiWin *w, int lx, int ly) {
    int slot = w->type - SCRIPTWIN_BASE;
    if (slot < 0 || slot >= SCRIPTWIN_N) return;
    ScriptWin *sw = &s_wins[slot];
    int ry = ly - 30;
    for (int i = 0; i < sw->item_count; ++i) {
        SwItem *it = &sw->items[i];
        if (it->kind != 3) continue;
        if (lx >= it->x && lx < it->x + it->w &&
            ry >= it->y && ry < it->y + it->h) {
            if (it->ctrl_id >= 0 && it->ctrl_id < SW_ITEMS &&
                sw->click_label[it->ctrl_id][0])
                fire_event(sw->click_label[it->ctrl_id]);
            else if (sw->click_label_generic[0])
                fire_event(sw->click_label_generic);
            return;
        }
    }
}

static void sw_key(GuiWin *w, EFI_INPUT_KEY key) {
    int slot = w->type - SCRIPTWIN_BASE;
    if (slot < 0 || slot >= SCRIPTWIN_N) return;
    ScriptWin *sw = &s_wins[slot];
    if (!sw->key_label[0]) return;
    char k[2] = { (key.UnicodeChar >= 32 && key.UnicodeChar < 127)
                    ? (char)key.UnicodeChar : '?', 0 };
    script_var_set("EV_KEY", k);
    fire_event(sw->key_label);
}

/* ---------- 从 cache 找 :label 并执行到 ret ---------- */
static void run_label(const CHAR16 *label) {
    if (s_call_depth >= 6 || !s_script_len) return;
    char target[64]; int i = 0;
    while (label[i] && i < 63) { target[i] = (char)label[i]; ++i; }
    target[i] = 0;

    char *p = s_script_cache, *found = NULL;
    while (*p) {
        char *ls = p;
        while (*p && *p != '\n') ++p;
        char *le = p;
        if (*p) ++p;
        char *q = ls;
        while (q < le && (*q == ' ' || *q == '\t')) ++q;
        if (q < le && *q == ':') {
            char lbl[64]; int n = 0; ++q;
            while (q < le && *q != ' ' && *q != '\r' && n < 63) lbl[n++] = *q++;
            lbl[n] = 0;
            if (!scmp(lbl, target)) { found = p; break; }
        }
    }
    if (!found) return;

    ++s_call_depth;
    char *p2 = found;
    while (*p2) {
        char *ls = p2;
        while (*p2 && *p2 != '\n') ++p2;
        char *le = p2;
        char saved = *le;
        *le = 0;
        char *s = ls;
        while (*s == ' ' || *s == '\t') ++s;
        if (*s && *s != '#' && *s != ':') {
            if (!scmp(s, "ret")) { *le = saved; break; }
            /* ★ 修 Bug3：复制到本地 buffer，避免 strim 改坏脚本缓存 */
            char local[512];
            scopy(local, sizeof(local), s);
            script_exec_line(local);
        }
        *le = saved;
        if (saved) p2 = le + 1; else break;
    }
    --s_call_depth;
}

/* ---------- 打开脚本窗口（由 win_open 分流） ---------- */
static int sw_open_window(int type) {
    int slot = type - SCRIPTWIN_BASE;
    if (slot < 0 || slot >= SCRIPTWIN_N) return -1;
    ScriptWin *sw = &s_wins[slot];
    if (!sw->alive) return -1;
    for (int i = 0; i < WIN_MAX; ++i)
        if (wins[i].alive && wins[i].type == type) {
            focus_win = i; wins[i].z = ++z_top; return i;
        }
    for (int i = 0; i < WIN_MAX; ++i) {
        if (wins[i].alive) continue;
        GuiWin *w = &wins[i];
        for (UINTN k = 0; k < sizeof(GuiWin); ++k) ((UINT8 *)w)[k] = 0;
        w->type = type; w->alive = 1;
        w->x = 100 + slot * 30;
        w->y = 100 + slot * 30;
        w->w = sw->w;
        w->h = sw->h;
        w->on_draw  = sw_draw;
        w->on_click = sw_click;
        w->on_key   = sw_key;
        w->z = ++z_top; focus_win = i;
        return i;
    }
    return -1;
}

/* ---------- 命令解析辅助 ---------- */
static CHAR16 *wnext_token(CHAR16 *p, CHAR16 *out, int cap) {
    while (*p == L' ') ++p;
    int i = 0;
    while (*p && *p != L' ' && i + 1 < cap) out[i++] = *p++;
    out[i] = 0;
    while (*p == L' ') ++p;
    return p;
}
static int wtoken_int(CHAR16 **p) {
    CHAR16 buf[32]; *p = wnext_token(*p, buf, 32);
    int n = 0, sign = 1, i = 0;
    if (buf[0] == L'-') { sign = -1; i = 1; }
    for (; buf[i]; ++i) {
        if (buf[i] < L'0' || buf[i] > L'9') break;
        n = n * 10 + (int)(buf[i] - L'0');
    }
    return n * sign;
}
static void wtoken_str(CHAR16 **p, char *out, int cap) {
    CHAR16 buf[256]; *p = wnext_token(*p, buf, 256);
    int i = 0;
    while (buf[i] && i + 1 < cap) { out[i] = (char)buf[i]; ++i; }
    out[i] = 0;
}
static void wtoken_rest(CHAR16 *p, char *out, int cap) {
    while (*p == L' ') ++p;
    int i = 0;
    while (*p && i + 1 < cap) { out[i++] = (*p < 128) ? (char)*p : '?'; ++p; }
    out[i] = 0;
}

/* ---------- 命令入口 ---------- */
static void win_api_cmd(CHAR16 *args) {
    CHAR16 sbuf[32]; args = wnext_token(args, sbuf, 32);
    char sub[32]; int i = 0;
    while (sbuf[i] && i < 31) { sub[i] = (char)sbuf[i]; ++i; }
    sub[i] = 0;

    if (!scmp(sub, "create")) {
        int slot = wtoken_int(&args);
        char tzh[64], ten[64];
        wtoken_str(&args, tzh, 64);
        wtoken_str(&args, ten, 64);
        int ww = wtoken_int(&args), hh = wtoken_int(&args);
        if (slot < 0 || slot >= SCRIPTWIN_N) return;
        ScriptWin *sw = &s_wins[slot];
        sw->alive = 1; sw->w = ww; sw->h = hh;
        sw_copy16(sw->title_zh, SW_TITLE_LEN, tzh);
        sw_copy16(sw->title_en, SW_TITLE_LEN, ten);
        sw->item_count = 0;
        for (int k = 0; k < SW_ITEMS; ++k) sw->click_label[k][0] = 0;
        sw->click_label_generic[0] = 0;
        sw->close_label[0] = 0;
        sw->key_label[0] = 0;
        return;
    }

    int slot = wtoken_int(&args);
    if (slot < 0 || slot >= SCRIPTWIN_N) return;
    ScriptWin *sw = &s_wins[slot];
    if (!sw->alive) return;

    if (!scmp(sub, "rect") || !scmp(sub, "border")) {
        int x = wtoken_int(&args), y = wtoken_int(&args);
        int ww = wtoken_int(&args), hh = wtoken_int(&args);
        char col[16]; wtoken_str(&args, col, 16);
        if (sw->item_count < SW_ITEMS) {
            SwItem *it = &sw->items[sw->item_count++];
            it->kind = (sub[0] == 'r') ? 0 : 2;
            it->x = x; it->y = y; it->w = ww; it->h = hh;
            it->color = sw_parse_color(col);
            it->ctrl_id = 0; it->text[0] = 0;
        }
        return;
    }
    if (!scmp(sub, "text")) {
        int x = wtoken_int(&args), y = wtoken_int(&args);
        char col[16]; wtoken_str(&args, col, 16);
        char txt[SW_TEXT_LEN]; wtoken_rest(args, txt, SW_TEXT_LEN);
        if (sw->item_count < SW_ITEMS) {
            SwItem *it = &sw->items[sw->item_count++];
            it->kind = 1; it->x = x; it->y = y; it->w = 0; it->h = 16;
            it->color = sw_parse_color(col);
            it->ctrl_id = 0;
            sw_copy16(it->text, SW_TEXT_LEN, txt);
        }
        return;
    }
    if (!scmp(sub, "button")) {
        int ctrl = wtoken_int(&args);
        int x = wtoken_int(&args), y = wtoken_int(&args);
        int ww = wtoken_int(&args), hh = wtoken_int(&args);
        char col[16]; wtoken_str(&args, col, 16);
        char txt[SW_TEXT_LEN]; wtoken_rest(args, txt, SW_TEXT_LEN);
        if (sw->item_count < SW_ITEMS) {
            SwItem *it = &sw->items[sw->item_count++];
            it->kind = 3; it->x = x; it->y = y; it->w = ww; it->h = hh;
            it->ctrl_id = ctrl; it->color = sw_parse_color(col);
            sw_copy16(it->text, SW_TEXT_LEN, txt);
        }
        return;
    }
    if (!scmp(sub, "on_click")) {
        int ctrl = wtoken_int(&args);
        CHAR16 tmp[64]; wnext_token(args, tmp, 64);
        CHAR16 *dst = (ctrl >= 0 && ctrl < SW_ITEMS)
                      ? sw->click_label[ctrl]
                      : sw->click_label_generic;
        int n = 0;
        while (tmp[n] && n < SW_LABEL_LEN - 1) { dst[n] = tmp[n]; ++n; }
        dst[n] = 0;
        return;
    }
    if (!scmp(sub, "on_close") || !scmp(sub, "on_key")) {
        CHAR16 tmp[64]; wnext_token(args, tmp, 64);
        CHAR16 *dst = (!scmp(sub, "on_close")) ? sw->close_label : sw->key_label;
        int n = 0;
        while (tmp[n] && n < SW_LABEL_LEN - 1) { dst[n] = tmp[n]; ++n; }
        dst[n] = 0;
        return;
    }
    if (!scmp(sub, "show"))    { win_open(SCRIPTWIN_BASE + slot); return; }
    if (!scmp(sub, "close") || !scmp(sub, "destroy")) {
        for (int k = 0; k < WIN_MAX; ++k)
            if (wins[k].alive && wins[k].type == SCRIPTWIN_BASE + slot) win_close(k);
        if (!scmp(sub, "destroy")) sw->alive = 0;
        return;
    }
    if (!scmp(sub, "clear"))   { sw->item_count = 0; return; }
    if (!scmp(sub, "repaint")) { /* 下一帧自动重绘 */ return; }
}

#endif /* WCT_WIN_API_H */