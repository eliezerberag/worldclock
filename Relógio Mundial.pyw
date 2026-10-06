"""Widgets de relógio mundial para o desktop do Windows.

Cada relógio é uma janela sem borda que pode ser arrastada com o mouse.
Clique com o botão direito em um relógio para ver as opções, abrir as
configurações de localidades ou o conversor de horário.
As posições e cidades ficam salvas em config.json, ao lado deste arquivo.

Correções aplicadas nesta versão (ver histórico da revisão):
  1. Corrida na busca online de cidades (search_future invalidado).
  2. ValueError em SettingsWindow.show(select=...) e em save_location.
  3. place_on_desktop não promove o relógio para o topo quando a janela
     imediatamente acima do desktop for topmost.
  4. save_config agora é atômico (tmp + os.replace).
  5. zone_choices() memoizado.
  6. Fallback para DEFAULT_CONFIG é persistido em disco.
  7. ClockWidget tolera cfg sem "x"/"y" e coordenadas float.
  8. App.tick pula relógios ocultos.
  9. SettingsWindow.close cancela a busca em andamento.
"""
import ctypes
import ctypes.wintypes as wt
import json
import os
import sys
import re
import tkinter as tk
import unicodedata
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, ttk
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError, available_timezones

# Empacotado (PyInstaller), __file__ aponta para uma pasta temporária; o config.json
# deve ficar ao lado do .exe.
if getattr(sys, "frozen", False):
    APP_DIR = Path(sys.executable).resolve().parent
else:
    APP_DIR = Path(__file__).resolve().parent
CONFIG_PATH = APP_DIR / "config.json"

DEFAULT_CONFIG = {
    "always_on_top": False,
    "clocks": [
        {"label": "São Paulo", "tz": "America/Sao_Paulo"},
        {"label": "Nova York", "tz": "America/New_York"},
        {"label": "Londres", "tz": "Europe/London"},
        {"label": "Tóquio", "tz": "Asia/Tokyo"},
    ],
}

# Nomes em português para a busca de fusos (os fusos IANA usam nomes em inglês).
CITY_ALIASES = {
    "São Paulo": "America/Sao_Paulo", "Rio de Janeiro": "America/Sao_Paulo",
    "Brasília": "America/Sao_Paulo", "Belo Horizonte": "America/Sao_Paulo",
    "Porto Alegre": "America/Sao_Paulo", "Curitiba": "America/Sao_Paulo",
    "Salvador": "America/Bahia", "Recife": "America/Recife", "Fortaleza": "America/Fortaleza",
    "Belém": "America/Belem", "Manaus": "America/Manaus", "Cuiabá": "America/Cuiaba",
    "Campo Grande": "America/Campo_Grande", "Porto Velho": "America/Porto_Velho",
    "Rio Branco": "America/Rio_Branco", "Fernando de Noronha": "America/Noronha",
    "Buenos Aires": "America/Argentina/Buenos_Aires", "Santiago": "America/Santiago",
    "Montevidéu": "America/Montevideo", "Assunção": "America/Asuncion", "Lima": "America/Lima",
    "Bogotá": "America/Bogota", "Caracas": "America/Caracas", "La Paz": "America/La_Paz",
    "Cidade do México": "America/Mexico_City", "Nova York": "America/New_York",
    "Miami": "America/New_York", "Washington": "America/New_York", "Chicago": "America/Chicago",
    "Denver": "America/Denver", "Phoenix": "America/Phoenix", "Los Angeles": "America/Los_Angeles",
    "São Francisco": "America/Los_Angeles", "Toronto": "America/Toronto",
    "Vancouver": "America/Vancouver", "Honolulu": "Pacific/Honolulu",
    "Londres": "Europe/London", "Dublin": "Europe/Dublin", "Lisboa": "Europe/Lisbon",
    "Madri": "Europe/Madrid", "Barcelona": "Europe/Madrid", "Paris": "Europe/Paris",
    "Bruxelas": "Europe/Brussels", "Amsterdã": "Europe/Amsterdam", "Berlim": "Europe/Berlin",
    "Frankfurt": "Europe/Berlin", "Munique": "Europe/Berlin", "Zurique": "Europe/Zurich",
    "Roma": "Europe/Rome", "Milão": "Europe/Rome", "Viena": "Europe/Vienna",
    "Varsóvia": "Europe/Warsaw", "Atenas": "Europe/Athens", "Estocolmo": "Europe/Stockholm",
    "Kiev": "Europe/Kyiv", "Moscou": "Europe/Moscow", "Istambul": "Europe/Istanbul",
    "Cairo": "Africa/Cairo", "Lagos": "Africa/Lagos", "Luanda": "Africa/Luanda",
    "Maputo": "Africa/Maputo", "Joanesburgo": "Africa/Johannesburg", "Nairóbi": "Africa/Nairobi",
    "Dubai": "Asia/Dubai", "Tel Aviv": "Asia/Jerusalem", "Riad": "Asia/Riyadh",
    "Nova Délhi": "Asia/Kolkata", "Mumbai": "Asia/Kolkata", "Bangkok": "Asia/Bangkok",
    "Cingapura": "Asia/Singapore", "Hong Kong": "Asia/Hong_Kong", "Pequim": "Asia/Shanghai",
    "Xangai": "Asia/Shanghai", "Shenzhen": "Asia/Shanghai", "Taipé": "Asia/Taipei",
    "Seul": "Asia/Seoul", "Tóquio": "Asia/Tokyo", "Sydney": "Australia/Sydney",
    "Melbourne": "Australia/Melbourne", "Perth": "Australia/Perth",
    "Auckland": "Pacific/Auckland", "UTC": "UTC",
}
GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
ZONE_REGIONS = ("Africa/", "America/", "Antarctica/", "Asia/", "Atlantic/", "Australia/",
                "Europe/", "Indian/", "Pacific/")

# Dimensões em pixels a 100% de escala; multiplicadas pela escala do monitor.
WIDTH, HEIGHT, RADIUS = 240, 110, 16

KEY = "#010203"  # cor que o Windows torna transparente (cantos arredondados)
BG = "#1e1f24"
FG = "#f2f2f5"
FG_DIM = "#9a9cab"
DAY = "#f5c542"
NIGHT = "#8fa8ff"

WEEKDAYS = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]
MONTHS = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]


def load_config():
    if CONFIG_PATH.exists():
        try:
            config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            if config.get("clocks"):
                config.setdefault("always_on_top", False)
                return config
        except (json.JSONDecodeError, OSError):
            pass
    return json.loads(json.dumps(DEFAULT_CONFIG))


def save_config(config):
    """Grava config.json de forma atômica: escreve num .tmp e renomeia por cima."""
    data = json.dumps(config, ensure_ascii=False, indent=2)
    tmp = CONFIG_PATH.with_name(CONFIG_PATH.name + ".tmp")
    tmp.write_text(data, encoding="utf-8")
    os.replace(tmp, CONFIG_PATH)


def rounded_rect(canvas, x1, y1, x2, y2, r, **kwargs):
    points = [
        x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
        x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
        x1, y2, x1, y2 - r, x1, y1 + r, x1, y1,
    ]
    return canvas.create_polygon(points, smooth=True, **kwargs)


def offset_text(reference, there):
    minutes = int((there.utcoffset() - reference.utcoffset()).total_seconds() // 60)
    if minutes == 0:
        return "mesmo horário"
    sign = "+" if minutes > 0 else "−"
    h, m = divmod(abs(minutes), 60)
    return f"{sign}{h}h{m:02d}" if m else f"{sign}{h}h"


def date_text(dt):
    return f"{WEEKDAYS[dt.weekday()]}, {dt.day:02d} {MONTHS[dt.month - 1]}"


def is_daytime(dt):
    return 6 <= dt.hour < 18


def normalize(text):
    text = unicodedata.normalize("NFKD", text.lower())
    return "".join(ch for ch in text if not unicodedata.combining(ch)).replace("_", " ")


_ZONE_CHOICES_CACHE = None


def zone_choices():
    """Lista (texto exibido, nome sugerido, fuso) com as cidades em português primeiro.

    O resultado é memoizado: available_timezones() é relativamente caro e o
    conjunto de fusos não muda durante a execução.
    """
    global _ZONE_CHOICES_CACHE
    if _ZONE_CHOICES_CACHE is not None:
        return _ZONE_CHOICES_CACHE
    choices = [(f"{name}  —  {tz}", name, tz) for name, tz in sorted(CITY_ALIASES.items())]
    for tz in sorted(available_timezones()):
        if tz.startswith(ZONE_REGIONS):
            choices.append((tz, tz.rsplit("/", 1)[-1].replace("_", " "), tz))
    _ZONE_CHOICES_CACHE = choices
    return choices


def search_cities(query):
    """Busca cidades no mundo todo (Open-Meteo) e devolve (texto, nome, fuso)."""
    url = GEOCODING_URL + "?" + urllib.parse.urlencode(
        {"name": query, "count": 15, "language": "pt", "format": "json"})
    with urllib.request.urlopen(url, timeout=8) as response:
        data = json.load(response)
    choices = []
    for r in data.get("results", []):
        tz = r.get("timezone")
        try:
            ZoneInfo(tz)
        except (ZoneInfoNotFoundError, ValueError, TypeError):
            continue
        place = ", ".join(p for p in (r.get("admin1"), r.get("country")) if p)
        choices.append((f"{r['name']}  —  {place}  ({tz})", r["name"], tz))
    return choices


def parse_time(text):
    """Aceita 9, 9:30, 0930, 21h, 21h30."""
    match = re.fullmatch(r"(\d{1,2})(?:[:h]?(\d{2}))?h?", text.strip().lower())
    if not match:
        return None
    hour, minute = int(match.group(1)), int(match.group(2) or 0)
    return (hour, minute) if hour < 24 and minute < 60 else None


def parse_date(text, default_year):
    """Aceita dd/mm ou dd/mm/aaaa."""
    match = re.fullmatch(r"(\d{1,2})/(\d{1,2})(?:/(\d{2}|\d{4}))?", text.strip())
    if not match:
        return None
    day, month = int(match.group(1)), int(match.group(2))
    year = int(match.group(3)) if match.group(3) else default_year
    if year < 100:
        year += 2000
    try:
        return datetime(year, month, day).date()
    except ValueError:
        return None


# --- Win32: manter os relógios logo acima da área de trabalho ----------------
user32 = ctypes.windll.user32
user32.GetAncestor.argtypes = [wt.HWND, wt.UINT]
user32.GetAncestor.restype = wt.HWND
user32.GetWindow.argtypes = [wt.HWND, wt.UINT]
user32.GetWindow.restype = wt.HWND
user32.GetShellWindow.restype = wt.HWND
user32.IsWindowVisible.argtypes = [wt.HWND]
user32.IsIconic.argtypes = [wt.HWND]
user32.GetWindowLongW.argtypes = [wt.HWND, ctypes.c_int]
user32.SetWindowPos.argtypes = [wt.HWND, wt.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                ctypes.c_int, wt.UINT]
GA_ROOT, GW_HWNDNEXT, GW_HWNDPREV = 2, 2, 3
GWL_EXSTYLE, WS_EX_TOPMOST = -20, 0x8
SWP_FLAGS = 0x0001 | 0x0002 | 0x0010 | 0x0200  # NOSIZE | NOMOVE | NOACTIVATE | NOOWNERZORDER


def sits_on_desktop(hwnd, desktop, ours):
    """True se, abaixo deste relógio, só houver outros relógios até chegar à área de trabalho."""
    below = user32.GetWindow(hwnd, GW_HWNDNEXT)
    while below:
        if below == desktop:
            return True
        if below not in ours and user32.IsWindowVisible(below) and not user32.IsIconic(below):
            return False  # há uma janela aberta embaixo: o relógio está por cima dela
        below = user32.GetWindow(below, GW_HWNDNEXT)
    return False  # a área de trabalho está por cima (ex.: Win+D)


def place_on_desktop(hwnd, desktop):
    """Coloca a janela imediatamente acima da área de trabalho na ordem de empilhamento.

    Se a janela imediatamente acima do desktop for topmost (situação incomum),
    não há um alvo seguro: inserir logo abaixo dela nos promoveria à faixa
    topmost. Nesse caso, deixamos a janela onde está e tentamos de novo no
    próximo ciclo.
    """
    above = user32.GetWindow(desktop, GW_HWNDPREV)
    if above == hwnd:
        return
    if not above:
        return  # nada seguro acima do desktop
    if user32.GetWindowLongW(above, GWL_EXSTYLE) & WS_EX_TOPMOST:
        return  # evitar virar topmost
    user32.SetWindowPos(hwnd, above, 0, 0, 0, 0, SWP_FLAGS)


class ClockWidget:
    def __init__(self, app, cfg):
        self.app = app
        self.cfg = cfg
        self.tz = ZoneInfo(cfg["tz"])
        self.dragging = False
        self.group = [self]
        s = app.scale
        w, h = int(WIDTH * s), int(HEIGHT * s)

        # Posição: tolera config antigo/editado à mão sem "x"/"y" ou com floats.
        x = int(cfg.get("x", 40 * s))
        y = int(cfg.get("y", 40 * s))
        cfg["x"], cfg["y"] = x, y

        self.win = win = tk.Toplevel(app.root)
        win.overrideredirect(True)
        win.configure(bg=KEY)
        win.attributes("-transparentcolor", KEY)
        win.attributes("-alpha", 0.92)
        win.attributes("-topmost", app.config["always_on_top"])
        win.geometry(f"{w}x{h}+{x}+{y}")
        if cfg.get("hidden"):
            win.withdraw()

        self.canvas = c = tk.Canvas(win, width=w, height=h, bg=KEY, highlightthickness=0)
        c.pack()
        rounded_rect(c, 0, 0, w, h, RADIUS * s, fill=BG)
        self.label = c.create_text(16 * s, 20 * s, anchor="w", text=cfg["label"], fill=FG_DIM,
                                   font=("Segoe UI Semibold", 11))
        self.icon = c.create_text(w - 16 * s, 20 * s, anchor="e", font=("Segoe UI Symbol", 12))
        self.time = c.create_text(14 * s, 56 * s, anchor="w", fill=FG, font=("Segoe UI Light", 26))
        self.info = c.create_text(16 * s, 92 * s, anchor="w", fill=FG_DIM, font=("Segoe UI", 9))

        c.bind("<ButtonPress-1>", self.start_drag)
        c.bind("<B1-Motion>", self.drag)
        c.bind("<ButtonRelease-1>", self.end_drag)
        c.bind("<Button-3>", self.show_menu)

    def set_location(self, label, tz):
        self.tz = ZoneInfo(tz)
        self.cfg["label"], self.cfg["tz"] = label, tz
        self.canvas.itemconfigure(self.label, text=label)

    @property
    def hidden(self):
        return self.cfg.get("hidden", False)

    def set_hidden(self, hidden):
        if hidden:
            self.cfg["hidden"] = True
            self.win.withdraw()
        else:
            self.cfg.pop("hidden", None)
            self.win.deiconify()
            self.win.attributes("-topmost", self.app.config["always_on_top"])

    def update(self, now_local):
        now = now_local.astimezone(self.tz)
        day = is_daytime(now)
        c = self.canvas
        c.itemconfigure(self.time, text=now.strftime("%H:%M:%S"))
        c.itemconfigure(self.icon, text="☀" if day else "☾", fill=DAY if day else NIGHT)
        c.itemconfigure(self.info, text=f"{date_text(now)}  ·  {offset_text(now_local, now)}")

    # --- arrastar ---------------------------------------------------------
    @property
    def hwnd(self):
        return user32.GetAncestor(self.win.winfo_id(), GA_ROOT)

    def start_drag(self, event):
        self._drag_offset = (event.x, event.y)
        # com "Mover todos juntos" ligado, ou segurando Ctrl, o grupo inteiro acompanha
        together = self.app.together_var.get() or event.state & 0x0004
        self.group = [w for w in self.app.widgets if not w.hidden] if together else [self]
        self._start = {w: (w.win.winfo_x(), w.win.winfo_y()) for w in self.group}
        for widget in self.group:
            widget.dragging = True

    def drag(self, event):
        dx, dy = self._drag_offset
        x = self.win.winfo_pointerx() - dx
        y = self.win.winfo_pointery() - dy
        if len(self.group) == 1:
            x, y = self.snap(x, y)
            self.win.geometry(f"+{int(x)}+{int(y)}")
            return
        sx, sy = self._start[self]
        for widget, (wx, wy) in self._start.items():
            widget.win.geometry(f"+{int(wx + x - sx)}+{int(wy + y - sy)}")

    def end_drag(self, _event):
        for widget in self.group:
            widget.dragging = False
            widget.cfg["x"], widget.cfg["y"] = widget.win.winfo_x(), widget.win.winfo_y()
        self.app.save()
        self.app.keep_on_desktop()

    def snap(self, x, y):
        """Ímã: encaixa alinhado ou lado a lado com um relógio próximo."""
        s = self.app.scale
        reach, gap = 18 * s, int(10 * s)
        w, h = self.win.winfo_width(), self.win.winfo_height()
        best_dx = best_dy = None
        for other in self.app.widgets:
            if other is self or other.hidden:
                continue
            ox, oy = other.win.winfo_x(), other.win.winfo_y()
            near = (x < ox + w + gap + reach and ox < x + w + gap + reach
                    and y < oy + h + gap + reach and oy < y + h + gap + reach)
            if not near:
                continue
            for target in (ox, ox + w + gap, ox - w - gap):
                d = target - x
                if abs(d) < reach and (best_dx is None or abs(d) < abs(best_dx)):
                    best_dx = d
            for target in (oy, oy + h + gap, oy - h - gap):
                d = target - y
                if abs(d) < reach and (best_dy is None or abs(d) < abs(best_dy)):
                    best_dy = d
        return x + (best_dx or 0), y + (best_dy or 0)

    # --- menu -------------------------------------------------------------
    def show_menu(self, event):
        menu = tk.Menu(self.win, tearoff=0)
        menu.add_command(label="Configurar localidades…",
                         command=lambda: self.app.open_settings("locations", select=self))
        menu.add_command(label="Converter horário…", command=lambda: self.app.open_settings("converter"))
        menu.add_command(label=f"Ocultar “{self.cfg['label']}”",
                         command=lambda: self.app.set_hidden(self, True))
        arrange = tk.Menu(menu, tearoff=0)
        arrange.add_command(label="Em coluna", command=lambda: self.app.arrange("column"))
        arrange.add_command(label="Em linha", command=lambda: self.app.arrange("row"))
        menu.add_cascade(label="Alinhar relógios", menu=arrange)
        menu.add_checkbutton(label="Mover todos juntos  (ou arraste com Ctrl)",
                             variable=self.app.together_var, command=self.app.toggle_together)
        menu.add_separator()
        menu.add_checkbutton(label="Sempre no topo", variable=self.app.on_top_var,
                             command=self.app.toggle_on_top)
        menu.add_separator()
        menu.add_command(label="Sair", command=self.app.root.destroy)
        menu.tk_popup(event.x_root, event.y_root)

    def destroy(self):
        self.win.destroy()


class SettingsWindow:
    """Janela com as abas Localidades e Converter."""

    LOCAL = "Meu horário (este computador)"

    def __init__(self, app):
        self.app = app
        self.editing = None  # ClockWidget sendo editado; None = nova localidade
        self.selected_tz = None
        self.auto_name = ""  # último nome preenchido automaticamente
        self.choices = zone_choices()
        self.online_choices = []
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.search_job = None
        self.search_future = None

        self.win = win = tk.Toplevel(app.root)
        win.title("Relógio Mundial")
        win.minsize(int(640 * app.scale), int(420 * app.scale))
        win.protocol("WM_DELETE_WINDOW", self.close)
        ttk.Style(win).configure("Treeview", rowheight=int(24 * app.scale))

        self.notebook = ttk.Notebook(win)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=10)
        self.locations_tab = ttk.Frame(self.notebook, padding=10)
        self.converter_tab = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(self.locations_tab, text="Localidades")
        self.notebook.add(self.converter_tab, text="Converter horário")
        self.build_locations()
        self.build_converter()
        self.refresh()
        self.new_location()

    def show(self, tab, select=None):
        self.notebook.select(self.locations_tab if tab == "locations" else self.converter_tab)
        if select is not None and select in self.app.widgets:
            try:
                self.tree.selection_set(str(self.app.widgets.index(select)))
            except ValueError:
                pass
        self.win.deiconify()
        self.win.lift()
        self.win.focus_force()

    def close(self):
        self.app.settings = None
        # Marca a busca em voo como obsoleta e cancela o que ainda está na fila.
        if self.search_future is not None:
            self.search_future.cancel()
            self.search_future = None
        self.executor.shutdown(wait=False, cancel_futures=True)
        self.win.destroy()

    # --- aba Localidades --------------------------------------------------
    def build_locations(self):
        tab = self.locations_tab
        tab.columnconfigure(0, weight=3)
        tab.columnconfigure(1, weight=2)
        tab.rowconfigure(0, weight=1)

        left = ttk.Frame(tab)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        left.rowconfigure(0, weight=1)
        left.columnconfigure(0, weight=1)
        self.tree = ttk.Treeview(left, columns=("shown", "label", "tz", "now"), show="headings",
                                 selectmode="browse")
        self.tree.tag_configure("hidden", foreground="#999")
        for col, title, width in (("shown", "Exibir", 50), ("label", "Localidade", 120),
                                  ("tz", "Fuso horário", 160), ("now", "Agora", 110)):
            self.tree.heading(col, text=title, anchor="w")
            self.tree.column(col, width=int(width * self.app.scale), anchor="w")
        self.tree.grid(row=0, column=0, sticky="nsew")
        self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)
        self.tree.bind("<Double-1>", lambda _e: self.toggle_hidden())
        buttons = ttk.Frame(left)
        buttons.grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Button(buttons, text="Nova localidade", command=self.new_location).pack(side="left")
        ttk.Button(buttons, text="Remover", command=self.remove_location).pack(side="left", padx=6)
        self.hide_button = ttk.Button(buttons, text="Ocultar", width=10, command=self.toggle_hidden,
                                      state="disabled")
        self.hide_button.pack(side="left")
        ttk.Label(left, text="Dica: clique duas vezes num relógio da lista para ocultar ou mostrar.",
                  foreground="#666").grid(row=2, column=0, sticky="w", pady=(6, 0))

        self.form = form = ttk.LabelFrame(tab, text="Nova localidade", padding=10)
        form.grid(row=0, column=1, sticky="nsew")
        form.columnconfigure(0, weight=1)
        form.rowconfigure(5, weight=1)
        ttk.Label(form, text="Nome exibido:").grid(row=0, column=0, sticky="w")
        self.name_var = tk.StringVar()
        self.name_entry = ttk.Entry(form, textvariable=self.name_var)
        self.name_entry.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(2, 8))
        ttk.Label(form, text="Buscar cidade (qualquer lugar do mundo):").grid(row=2, column=0, sticky="w")
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self.on_search_change())
        ttk.Entry(form, textvariable=self.search_var).grid(row=3, column=0, columnspan=2,
                                                           sticky="ew", pady=(2, 2))
        self.search_status = ttk.Label(form, text="", foreground="#666")
        self.search_status.grid(row=4, column=0, columnspan=2, sticky="w", pady=(0, 4))
        self.zone_list = tk.Listbox(form, height=10, activestyle="none", exportselection=False)
        self.zone_list.grid(row=5, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(form, orient="vertical", command=self.zone_list.yview)
        scroll.grid(row=5, column=1, sticky="ns")
        self.zone_list.configure(yscrollcommand=scroll.set)
        self.zone_list.bind("<<ListboxSelect>>", self.on_zone_select)
        self.zone_status = ttk.Label(form, text="", foreground="#666")
        self.zone_status.grid(row=6, column=0, columnspan=2, sticky="w", pady=(4, 8))
        ttk.Button(form, text="Salvar", command=self.save_location).grid(row=7, column=0,
                                                                        columnspan=2, sticky="e")
        self.filter_zones()

    def refresh(self):
        """Recarrega a lista de localidades e as opções do conversor."""
        selected = self.tree.selection()
        self.tree.delete(*self.tree.get_children())
        for i, widget in enumerate(self.app.widgets):
            self.tree.insert("", "end", iid=str(i), tags=("hidden",) if widget.hidden else (),
                             values=("" if widget.hidden else "✓", widget.cfg["label"],
                                     widget.cfg["tz"], ""))
        if selected and self.tree.exists(selected[0]):
            self.tree.selection_set(selected[0])
        self.update_times(datetime.now().astimezone())
        self.source_combo["values"] = [self.LOCAL] + [w.cfg["label"] for w in self.app.widgets]
        if self.source_var.get() not in self.source_combo["values"]:
            self.source_var.set(self.LOCAL)
        self.convert()

    def update_times(self, now_local):
        for i, widget in enumerate(self.app.widgets):
            now = now_local.astimezone(widget.tz)
            self.tree.set(str(i), "now", f"{now:%H:%M}  {date_text(now)}")

    def on_search_change(self):
        """Filtra a lista local na hora e agenda a busca online (após uma pausa na digitação)."""
        self.online_choices = []
        self.filter_zones()
        if self.search_job:
            self.win.after_cancel(self.search_job)
            self.search_job = None
        # Invalida qualquer busca em voo: quando o resultado chegar,
        # poll_online_search verá que não é mais o future atual e desistirá.
        self.search_future = None
        query = self.search_var.get().strip()
        if len(query) >= 3:
            self.search_status.configure(text="Buscando cidades…")
            self.search_job = self.win.after(400, lambda: self.start_online_search(query))
        else:
            self.search_status.configure(text="")

    def start_online_search(self, query):
        self.search_job = None
        self.search_future = future = self.executor.submit(search_cities, query)
        self.win.after(100, lambda: self.poll_online_search(future, query))

    def poll_online_search(self, future, query):
        if future is not self.search_future or not self.win.winfo_exists():
            return  # uma busca mais nova substituiu esta
        if not future.done():
            self.win.after(100, lambda: self.poll_online_search(future, query))
            return
        try:
            self.online_choices = future.result()
            found = len(self.online_choices)
            self.search_status.configure(
                text=f"{found} cidade(s) encontrada(s) para “{query}”." if found
                else f"Nenhuma cidade encontrada para “{query}”.")
        except Exception:
            self.online_choices = []
            self.search_status.configure(text="Sem conexão: mostrando só a lista local.")
        self.filter_zones()

    def filter_zones(self):
        query = normalize(self.search_var.get().strip())
        local = [c for c in self.choices if query in normalize(c[0])][:300]
        self.visible_choices = self.online_choices + local
        self.zone_list.delete(0, "end")
        for display, _name, _tz in self.visible_choices:
            self.zone_list.insert("end", display)

    def set_selected_tz(self, tz):
        self.selected_tz = tz
        if tz:
            now = datetime.now(ZoneInfo(tz))
            self.zone_status.configure(text=f"Selecionado: {tz}  ({now:%H:%M} agora)")
        else:
            self.zone_status.configure(text="Escolha um fuso na lista acima.")

    def on_zone_select(self, _event):
        sel = self.zone_list.curselection()
        if not sel:
            return
        _display, name, tz = self.visible_choices[sel[0]]
        self.set_selected_tz(tz)
        if self.name_var.get().strip() in ("", self.auto_name):
            self.name_var.set(name)
            self.auto_name = name

    def on_tree_select(self, _event):
        sel = self.tree.selection()
        if not sel:
            return
        self.editing = self.app.widgets[int(sel[0])]
        self.auto_name = ""
        self.hide_button.configure(state="normal",
                                   text="Mostrar" if self.editing.hidden else "Ocultar")
        self.form.configure(text=f"Editar “{self.editing.cfg['label']}”")
        self.name_var.set(self.editing.cfg["label"])
        self.search_var.set("")
        self.set_selected_tz(self.editing.cfg["tz"])

    def new_location(self):
        self.editing = None
        self.auto_name = ""
        self.hide_button.configure(state="disabled", text="Ocultar")
        self.tree.selection_remove(*self.tree.selection())
        self.form.configure(text="Nova localidade")
        self.name_var.set("")
        self.search_var.set("")
        self.set_selected_tz(None)
        self.name_entry.focus_set()

    def save_location(self):
        name = self.name_var.get().strip()
        if not name:
            messagebox.showwarning("Relógio Mundial", "Informe o nome exibido.", parent=self.win)
            return
        if not self.selected_tz:
            messagebox.showwarning("Relógio Mundial", "Escolha um fuso horário na lista.", parent=self.win)
            return
        if self.editing is not None and self.editing in self.app.widgets:
            self.app.update_clock(self.editing, name, self.selected_tz)
            index = self.app.widgets.index(self.editing)
        else:
            # "editing" apontava para um relógio removido nesse meio-tempo: trata como novo
            self.editing = None
            self.app.add_clock(name, self.selected_tz)
            index = len(self.app.widgets) - 1
        self.tree.selection_set(str(index))

    def toggle_hidden(self):
        sel = self.tree.selection()
        if not sel:
            return
        widget = self.app.widgets[int(sel[0])]
        self.app.set_hidden(widget, not widget.hidden, parent=self.win)
        if self.tree.exists(sel[0]):
            self.tree.selection_set(sel[0])
        self.hide_button.configure(text="Mostrar" if widget.hidden else "Ocultar")

    def remove_location(self):
        sel = self.tree.selection()
        if not sel:
            return
        widget = self.app.widgets[int(sel[0])]
        if self.app.remove_clock(widget, parent=self.win):
            self.new_location()

    # --- aba Converter ----------------------------------------------------
    def build_converter(self):
        tab = self.converter_tab
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(2, weight=1)

        inputs = ttk.Frame(tab)
        inputs.grid(row=0, column=0, sticky="ew")
        now = datetime.now()
        self.time_var = tk.StringVar(value=f"{now:%H:%M}")
        self.date_var = tk.StringVar(value=f"{now:%d/%m/%Y}")
        self.source_var = tk.StringVar(value=self.LOCAL)
        ttk.Label(inputs, text="Quando forem").pack(side="left")
        ttk.Entry(inputs, textvariable=self.time_var, width=7).pack(side="left", padx=4)
        ttk.Label(inputs, text="do dia").pack(side="left")
        ttk.Entry(inputs, textvariable=self.date_var, width=11).pack(side="left", padx=4)
        ttk.Label(inputs, text="em").pack(side="left")
        self.source_combo = ttk.Combobox(inputs, textvariable=self.source_var, state="readonly",
                                         width=28)
        self.source_combo.pack(side="left", padx=4)
        ttk.Button(inputs, text="Agora", command=self.reset_now).pack(side="left", padx=(8, 0))
        for var in (self.time_var, self.date_var, self.source_var):
            var.trace_add("write", lambda *_: self.convert())

        self.convert_status = ttk.Label(tab, text="", foreground="#666")
        self.convert_status.grid(row=1, column=0, sticky="w", pady=(8, 4))

        self.results = ttk.Treeview(tab, columns=("label", "time", "date", "diff"), show="headings")
        for col, title, width in (("label", "Localidade", 200), ("time", "Hora", 80),
                                  ("date", "Dia", 200), ("diff", "Diferença", 110)):
            self.results.heading(col, text=title, anchor="w")
            self.results.column(col, width=int(width * self.app.scale), anchor="w")
        self.results.grid(row=2, column=0, sticky="nsew")

    def reset_now(self):
        now = datetime.now()
        self.time_var.set(f"{now:%H:%M}")
        self.date_var.set(f"{now:%d/%m/%Y}")
        self.source_var.set(self.LOCAL)

    def convert(self):
        if not hasattr(self, "results"):
            return
        self.results.delete(*self.results.get_children())
        time = parse_time(self.time_var.get())
        date = parse_date(self.date_var.get(), datetime.now().year)
        if time is None or date is None:
            self.convert_status.configure(
                text="Digite a hora como 14:30 (ou 14h30) e a data como 25/12 ou 25/12/2026.")
            return

        naive = datetime(date.year, date.month, date.day, *time)
        source = self.source_var.get()
        if source == self.LOCAL:
            start = naive.astimezone()  # interpreta no fuso do computador
        else:
            widget = next((w for w in self.app.widgets if w.cfg["label"] == source), None)
            if widget is None:
                self.convert_status.configure(text=f"Localidade “{source}” não existe mais.")
                return
            start = naive.replace(tzinfo=widget.tz)
        self.convert_status.configure(text=f"{start:%H:%M} de {date_text(start)} em {source} equivale a:")

        rows = [(self.LOCAL, start.astimezone())]
        rows += [(w.cfg["label"], start.astimezone(w.tz)) for w in self.app.widgets]
        for label, dt in rows:
            day = date_text(dt)
            if dt.date() > start.date():
                day += "  (dia seguinte)"
            elif dt.date() < start.date():
                day += "  (dia anterior)"
            icon = "☀" if is_daytime(dt) else "☾"
            self.results.insert("", "end", values=(label, f"{dt:%H:%M}  {icon}", day,
                                                   offset_text(start, dt)))


class App:
    def __init__(self):
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)  # texto nítido em telas com escala
        except (AttributeError, OSError):
            pass

        self.root = tk.Tk()
        self.root.withdraw()
        # Ícone usado por todas as janelas; empacotado, fica em sys._MEIPASS.
        icon = Path(getattr(sys, "_MEIPASS", APP_DIR)) / "icone.ico"
        if icon.exists():
            self.root.iconbitmap(default=str(icon))
        self.scale = self.root.winfo_fpixels("1i") / 96
        self.config = load_config()
        self.on_top_var = tk.BooleanVar(value=self.config["always_on_top"])
        self.together_var = tk.BooleanVar(value=self.config.get("move_together", False))
        self.settings = None

        self.place_new(self.config["clocks"])
        self.widgets = []
        invalid = []
        for cfg in self.config["clocks"]:
            try:
                self.widgets.append(ClockWidget(self, cfg))
            except (ZoneInfoNotFoundError, ValueError, KeyError):
                invalid.append(cfg.get("label", "?"))
        if invalid:
            messagebox.showwarning("Relógio Mundial", "Fuso horário inválido em: " + ", ".join(invalid))
        if not self.widgets:
            self.config = json.loads(json.dumps(DEFAULT_CONFIG))
            self.place_new(self.config["clocks"])
            self.widgets = [ClockWidget(self, cfg) for cfg in self.config["clocks"]]
            self.save()  # persiste o fallback, para não repetir o aviso a cada início
        elif invalid:
            # Limpa entradas inválidas do config.
            self.save()
        if all(w.hidden for w in self.widgets):
            self.widgets[0].set_hidden(False)  # sem nenhum visível não há como abrir o menu

        self.tick()
        self.keep_on_desktop_loop()

    def keep_on_desktop(self):
        """Fora do modo "sempre no topo", deixa os relógios logo acima da área de trabalho:
        atrás de qualquer janela aberta, mas visíveis quando o desktop é exibido (Win+D)."""
        desktop = user32.GetShellWindow()
        if self.config["always_on_top"] or not desktop:
            return
        visible = [w for w in self.widgets if not w.hidden and not w.dragging]
        ours = {w.hwnd for w in self.widgets}
        for widget in visible:
            hwnd = widget.hwnd
            if not sits_on_desktop(hwnd, desktop, ours):
                place_on_desktop(hwnd, desktop)

    def keep_on_desktop_loop(self):
        self.keep_on_desktop()
        self.root.after(250, self.keep_on_desktop_loop)

    def place_new(self, clocks):
        """Empilha na lateral esquerda os relógios que ainda não têm posição."""
        step = int((HEIGHT + 14) * self.scale)
        for i, cfg in enumerate(clocks):
            cfg.setdefault("x", int(40 * self.scale))
            cfg.setdefault("y", int(40 * self.scale) + i * step)

    def tick(self):
        now_local = datetime.now().astimezone()
        for widget in self.widgets:
            if not widget.hidden:
                widget.update(now_local)
        if self.settings:
            self.settings.update_times(now_local)
        # agenda o próximo tique para logo após a virada do segundo
        self.root.after(1000 - datetime.now().microsecond // 1000 + 5, self.tick)

    def save(self):
        self.config["clocks"] = [w.cfg for w in self.widgets]
        save_config(self.config)

    def changed(self):
        self.save()
        for widget in self.widgets:
            if not widget.hidden:
                widget.update(datetime.now().astimezone())
        if self.settings:
            self.settings.refresh()

    def open_settings(self, tab, select=None):
        if self.settings is None:
            self.settings = SettingsWindow(self)
        self.settings.show(tab, select)

    def add_clock(self, label, tz):
        last = self.widgets[-1].cfg if self.widgets else {"x": 40, "y": 40}
        cfg = {"label": label, "tz": tz, "x": last["x"] + 30, "y": last["y"] + 30}
        self.widgets.append(ClockWidget(self, cfg))
        self.changed()

    def update_clock(self, widget, label, tz):
        widget.set_location(label, tz)
        self.changed()

    def arrange(self, direction):
        """Alinha os relógios visíveis a partir do canto superior esquerdo do grupo.

        Quando a coluna (ou linha) passa do limite da tela, começa outra ao lado (ou abaixo).
        """
        visible = [w for w in self.widgets if not w.hidden]
        if not visible:
            return
        gap = int(10 * self.scale)
        w, h = int(WIDTH * self.scale), int(HEIGHT * self.scale)
        left = min(v.win.winfo_x() for v in visible)
        top = min(v.win.winfo_y() for v in visible)
        bottom = self.root.winfo_vrooty() + self.root.winfo_screenheight() - int(48 * self.scale)
        right = self.root.winfo_vrootx() + self.root.winfo_screenwidth()
        x, y = left, top
        for widget in visible:
            if direction == "column" and y + h > bottom and y > top:
                x, y = x + w + gap, top
            elif direction == "row" and x + w > right and x > left:
                x, y = left, y + h + gap
            widget.win.geometry(f"+{int(x)}+{int(y)}")
            widget.cfg["x"], widget.cfg["y"] = x, y
            if direction == "column":
                y += h + gap
            else:
                x += w + gap
        self.save()

    def is_last_visible(self, widget):
        return not widget.hidden and sum(not w.hidden for w in self.widgets) == 1

    def set_hidden(self, widget, hidden, parent=None):
        if hidden and self.is_last_visible(widget):
            messagebox.showinfo(
                "Relógio Mundial",
                "É preciso deixar pelo menos um relógio visível: é por ele (botão direito) "
                "que você abre as configurações.",
                parent=parent)
            return
        widget.set_hidden(hidden)
        self.changed()

    def remove_clock(self, widget, parent=None):
        if self.is_last_visible(widget):
            messagebox.showinfo("Relógio Mundial", "É preciso manter pelo menos um relógio visível.",
                                parent=parent)
            return False
        if not messagebox.askyesno("Relógio Mundial", f"Remover “{widget.cfg['label']}”?", parent=parent):
            return False
        self.widgets.remove(widget)
        widget.destroy()
        self.changed()
        return True

    def toggle_together(self):
        self.config["move_together"] = self.together_var.get()
        self.save()

    def toggle_on_top(self):
        self.config["always_on_top"] = self.on_top_var.get()
        for widget in self.widgets:
            widget.win.attributes("-topmost", self.config["always_on_top"])
        self.save()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    App().run()