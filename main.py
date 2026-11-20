"""
Père Mehdi - Téléchargeur de vidéos YouTube / Facebook (MP4 ou MP3)
Fonctionne sur Windows (.exe) et Android (.apk) grâce à Flet + yt-dlp.
"""
import os
import sys
import shutil
import threading

import flet as ft
import yt_dlp

APP_NAME = "Père Mehdi"
IS_ANDROID = hasattr(sys, "getandroidapilevel") or "ANDROID_ROOT" in os.environ


# ---------------------------------------------------------------- utilitaires
def find_ffmpeg():
    """Cherche ffmpeg : d'abord à côté de l'exe (PyInstaller), puis dans le PATH."""
    candidates = []
    base = getattr(sys, "_MEIPASS", None)
    if base:
        candidates.append(os.path.join(base, "ffmpeg.exe"))
    candidates.append(os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "ffmpeg.exe"))
    for c in candidates:
        if os.path.isfile(c):
            return c
    return shutil.which("ffmpeg")


def default_folder():
    if IS_ANDROID:
        for p in ("/storage/emulated/0/Download/Pere Mehdi", "/sdcard/Download/Pere Mehdi"):
            try:
                os.makedirs(p, exist_ok=True)
                test = os.path.join(p, ".test")
                open(test, "w").close()
                os.remove(test)
                return p
            except Exception:
                continue
        p = os.path.join(os.environ.get("FLET_APP_STORAGE_DATA", os.getcwd()), "Telechargements")
    else:
        p = os.path.join(os.path.expanduser("~"), "Downloads", "Pere Mehdi")
    os.makedirs(p, exist_ok=True)
    return p


def platform_of(url):
    u = url.lower()
    if "youtu" in u:
        return "YouTube"
    if "facebook" in u or "fb.watch" in u or "fb.com" in u:
        return "Facebook"
    return None


# ---------------------------------------------------------------- interface
def main(page: ft.Page):
    page.title = APP_NAME
    page.theme_mode = ft.ThemeMode.LIGHT
    page.theme = ft.Theme(color_scheme_seed=ft.Colors.DEEP_ORANGE)
    page.padding = 20
    page.scroll = ft.ScrollMode.AUTO
    if not IS_ANDROID:
        page.window.width = 560
        page.window.height = 780

    ffmpeg = find_ffmpeg()
    folder = {"path": default_folder()}

    url_field = ft.TextField(
        label="Lien YouTube ou Facebook",
        hint_text="https://www.youtube.com/watch?v=...",
        prefix_icon=ft.Icons.LINK,
        expand=True,
    )

    fmt = ft.SegmentedButton(
        selected={"mp4"},
        segments=[
            ft.Segment(value="mp4", label=ft.Text("Vidéo MP4"), icon=ft.Icon(ft.Icons.MOVIE)),
            ft.Segment(value="mp3", label=ft.Text("Audio MP3"), icon=ft.Icon(ft.Icons.MUSIC_NOTE)),
        ],
    )

    quality = ft.Dropdown(
        label="Qualité vidéo",
        value="best",
        options=[
            ft.dropdown.Option("best", "Meilleure disponible"),
            ft.dropdown.Option("1080", "1080p"),
            ft.dropdown.Option("720", "720p"),
            ft.dropdown.Option("480", "480p"),
            ft.dropdown.Option("360", "360p"),
        ],
        width=220,
    )

    folder_text = ft.Text(folder["path"], size=12, selectable=True)
    title_text = ft.Text("", weight=ft.FontWeight.BOLD)
    thumb = ft.Image(src="", width=320, height=180, fit=ft.ImageFit.COVER,
                     border_radius=10, visible=False)
    progress = ft.ProgressBar(value=0, visible=False)
    status = ft.Text("", size=13)
    history = ft.Column(spacing=4)

    def set_status(msg, color=None):
        status.value = msg
        status.color = color
        page.update()

    # ----- choix du dossier (Windows)
    def on_folder(e: ft.FilePickerResultEvent):
        if e.path:
            folder["path"] = e.path
            folder_text.value = e.path
            page.update()

    picker = ft.FilePicker(on_result=on_folder)
    page.overlay.append(picker)

    def paste(e):
        try:
            txt = page.get_clipboard()
            if txt:
                url_field.value = txt.strip()
                page.update()
        except Exception:
            pass

    # ----- téléchargement
    def hook(d):
        if d.get("status") == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            done = d.get("downloaded_bytes", 0)
            if total:
                progress.value = done / total
                speed = d.get("speed") or 0
                status.value = f"Téléchargement… {done/total*100:.0f} %  ({speed/1e6:.1f} Mo/s)"
            else:
                progress.value = None
                status.value = f"Téléchargement… {done/1e6:.1f} Mo"
            page.update()
        elif d.get("status") == "finished":
            progress.value = None
            status.value = "Finalisation du fichier…"
            page.update()

    def build_options(mode):
        opts = {
            "outtmpl": os.path.join(folder["path"], "%(title).80s.%(ext)s"),
            "progress_hooks": [hook],
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "restrictfilenames": False,
            "windowsfilenames": True,
        }
        if ffmpeg:
            opts["ffmpeg_location"] = ffmpeg
        q = quality.value
        h = "" if q == "best" else f"[height<={q}]"

        if mode == "mp3":
            if ffmpeg:
                opts["format"] = "bestaudio/best"
                opts["postprocessors"] = [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }]
            else:
                # Pas de ffmpeg (Android) : audio M4A, lisible par tous les lecteurs
                opts["format"] = "bestaudio[ext=m4a]/bestaudio"
        else:
            if ffmpeg:
                opts["format"] = (f"bestvideo{h}[ext=mp4]+bestaudio[ext=m4a]/"
                                  f"best{h}[ext=mp4]/best{h}")
                opts["merge_output_format"] = "mp4"
            else:
                # Sans ffmpeg : format déjà fusionné (vidéo+son) en MP4
                opts["format"] = f"best{h}[ext=mp4][acodec!=none][vcodec!=none]/best[ext=mp4]/best"
        return opts

    def worker(url, mode):
        try:
            set_status("Analyse du lien…")
            with yt_dlp.YoutubeDL({"quiet": True, "noplaylist": True}) as ydl:
                info = ydl.extract_info(url, download=False)
            title_text.value = info.get("title", "")
            if info.get("thumbnail"):
                thumb.src = info["thumbnail"]
                thumb.visible = True
            page.update()

            with yt_dlp.YoutubeDL(build_options(mode)) as ydl:
                ydl.download([url])

            progress.value = 1
            ext = "MP3" if (mode == "mp3" and ffmpeg) else ("M4A" if mode == "mp3" else "MP4")
            set_status(f"✅ Terminé ! Fichier {ext} enregistré dans :\n{folder['path']}",
                       ft.Colors.GREEN_700)
            history.controls.insert(0, ft.ListTile(
                leading=ft.Icon(ft.Icons.MUSIC_NOTE if mode == "mp3" else ft.Icons.MOVIE),
                title=ft.Text(info.get("title", url), max_lines=1),
                subtitle=ft.Text(f"{platform_of(url)} • {ext}"),
                dense=True,
            ))
        except Exception as ex:
            msg = str(ex)
            if "private" in msg.lower() or "login" in msg.lower():
                msg = "Vidéo privée ou nécessitant une connexion : impossible de la télécharger."
            set_status(f"❌ Erreur : {msg[:300]}", ft.Colors.RED_700)
        finally:
            dl_btn.disabled = False
            progress.visible = progress.value is not None and progress.value > 0
            page.update()

    def start(e):
        url = (url_field.value or "").strip()
        if not url:
            set_status("Collez d'abord un lien.", ft.Colors.ORANGE_800)
            return
        if not platform_of(url):
            set_status("Lien non reconnu : utilisez un lien YouTube ou Facebook.", ft.Colors.ORANGE_800)
            return
        dl_btn.disabled = True
        progress.visible = True
        progress.value = None
        thumb.visible = False
        title_text.value = ""
        page.update()
        mode = list(fmt.selected)[0]
        threading.Thread(target=worker, args=(url, mode), daemon=True).start()

    dl_btn = ft.FilledButton("Télécharger", icon=ft.Icons.DOWNLOAD, on_click=start,
                             height=50, width=260)

    folder_btn = ft.OutlinedButton("Changer de dossier", icon=ft.Icons.FOLDER_OPEN,
                                   on_click=lambda e: picker.get_directory_path(),
                                   visible=not IS_ANDROID)

    note = None
    if not ffmpeg:
        note = ft.Text("ℹ️ Sur ce téléphone, l'option audio enregistre en M4A "
                       "(même qualité que le MP3, lisible partout).",
                       size=11, italic=True, color=ft.Colors.GREY_700)

    header = ft.Container(
        content=ft.Row([
            ft.Icon(ft.Icons.DOWNLOAD_FOR_OFFLINE, size=44, color=ft.Colors.WHITE),
            ft.Column([
                ft.Text(APP_NAME, size=26, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE),
                ft.Text("YouTube • Facebook  →  MP4 / MP3", color=ft.Colors.WHITE70),
            ], spacing=0),
        ]),
        padding=16,
        border_radius=14,
        gradient=ft.LinearGradient(colors=[ft.Colors.DEEP_ORANGE, ft.Colors.RED_700]),
    )

    page.add(
        header,
        ft.Container(height=10),
        ft.Row([url_field, ft.IconButton(ft.Icons.CONTENT_PASTE, tooltip="Coller",
                                         on_click=paste)]),
        fmt,
        quality,
        ft.Row([ft.Icon(ft.Icons.FOLDER, size=18), ft.Container(folder_text, expand=True)]),
        folder_btn,
        ft.Container(height=6),
        ft.Row([dl_btn], alignment=ft.MainAxisAlignment.CENTER),
        progress,
        status,
        *( [note] if note else [] ),
        title_text,
        thumb,
        ft.Divider(),
        ft.Text("Historique", weight=ft.FontWeight.BOLD),
        history,
    )


if __name__ == "__main__":
    ft.app(target=main)
