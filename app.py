import base64
import html
import mimetypes
import os
from email.parser import BytesParser
from email.policy import default
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from noita_wand_parser import find_thumbnail_for_action, parse_wands_from_folder

HOST = "0.0.0.0"
PORT = 8000
PROJECT_ROOT = Path(__file__).resolve().parent
THUMBNAIL_DIR = PROJECT_ROOT / "assets" / "thumbnails"
WAND_SPRITE_DIR = PROJECT_ROOT / "assets" / "wand_sprites"

INDEX_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Noita Wand Visualizer</title>
  <style>
    body {
      font-family: Arial, sans-serif;
      background: #1e120d;
      color: #f4e7d2;
      margin: 0;
      padding: 32px;
    }
    .container {
      max-width: 760px;
      margin: 0 auto;
      background: #2e2522;
      border: 1px solid #2e2522;
      border-radius: 12px;
      padding: 28px;
      box-shadow: 0 8px 20px rgba(0,0,0,0.2);
    }
    h1 {
      margin-top: 0;
      color: #f0b35c;
    }
    form {
      display: flex;
      flex-direction: column;
      gap: 16px;
    }
    input[type="file"] {
      padding: 12px;
      background: #261811;
      border: 1px solid #2e2522;
      border-radius: 8px;
      color: #f4e7d2;
    }
    .button-row {
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      align-items: center;
    }
    button {
      width: fit-content;
      padding: 12px 18px;
      background: #d08c3a;
      color: #1f120d;
      border: none;
      border-radius: 8px;
      cursor: pointer;
      font-weight: bold;
    }
    .hint {
      color: #d9b994;
      line-height: 1.6;
    }
    .note {
      color: #f3d1a7;
      font-size: 0.95rem;
    }
  </style>
</head>
<body>
  <div class="container">
    <h1>Noita Wand Visualizer</h1>
    <p class="hint">Upload one or more wand XML files, or a whole folder of wand exports, and see every wand contained inside.</p>
    <form method="post" action="/upload" enctype="multipart/form-data">
      <div class="button-row">
        <button type="button" id="folderPickerBtn">Select folder</button>
        <button type="button" id="filePickerBtn">Select XML files</button>
        <button type="submit">Parse wands</button>
      </div>
      <input id="folderPicker" type="file" name="bones_files" accept=".xml,.txt,.bin" multiple webkitdirectory directory style="display:none;">
      <input id="filePicker" type="file" name="bones_files" accept=".xml,.txt,.bin" multiple style="display:none;">
      <div id="uploadNote" class="note">Folder upload works in Chrome and Edge. Other browsers can still select multiple XML files.</div>
    </form>
  </div>

  <script>
    const supportsFolderPicker = 'webkitdirectory' in document.createElement('input') || 'directory' in document.createElement('input');
    const folderPicker = document.getElementById('folderPicker');
    const filePicker = document.getElementById('filePicker');
    const uploadNote = document.getElementById('uploadNote');

    document.getElementById('folderPickerBtn').addEventListener('click', function () {
      if (!supportsFolderPicker) {
        uploadNote.textContent = 'Folder upload is not supported in this browser. Please use “Select XML files” instead.';
        filePicker.click();
        return;
      }
      folderPicker.click();
    });

    document.getElementById('filePickerBtn').addEventListener('click', function () {
      filePicker.click();
    });

    folderPicker.addEventListener('change', function () {
      if (folderPicker.files && folderPicker.files.length) {
        uploadNote.textContent = 'Folder selected: ' + folderPicker.files.length + ' file(s) ready to parse.';
      }
    });

    filePicker.addEventListener('change', function () {
      if (filePicker.files && filePicker.files.length) {
        uploadNote.textContent = 'Files selected: ' + filePicker.files.length + ' file(s) ready to parse.';
      }
    });

    if (!supportsFolderPicker) {
      uploadNote.textContent = 'This browser does not support folder selection. Please choose multiple XML files instead.';
    }
  </script>
</body>
</html>
"""


def parse_upload_data(raw_data, content_type):
    header = f"Content-Type: {content_type}\r\n\r\n".encode("utf-8")
    message = BytesParser(policy=default).parsebytes(header + raw_data)
    result = {}
    for part in message.iter_parts():
        field_name = part.get_param("name", header="content-disposition")
        if not field_name:
            continue
        payload = part.get_payload(decode=True)
        filename = part.get_filename()
        result.setdefault(field_name, []).append({
            "filename": filename,
            "content": payload or b"",
        })
    return result


def to_data_uri(path):
    mime, _ = mimetypes.guess_type(path)
    mime = mime or "image/png"
    with open(path, "rb") as f:
        encoded = base64.b64encode(f.read()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def render_wand_stat(label, value):
    return (
        '<div style="min-width:120px; margin-right:20px; margin-bottom:12px;">'
        f'<div style="font-size:11px; text-transform:uppercase; letter-spacing:0.5px; color:#d9b994;">{html.escape(label)}</div>'
        f'<div style="font-size:15px; font-weight:600;">{html.escape(str(value))}</div>'
        '</div>'
    )


def spell_display_name(spell_id):
    return spell_id.replace("_", " ").title()


def render_spell_card(index, spell_id):
    thumb_path = find_thumbnail_for_action(spell_id, THUMBNAIL_DIR)
    if thumb_path:
        icon_html = f'<img src="{to_data_uri(thumb_path)}" alt="{html.escape(spell_display_name(spell_id))}" style="width:56px;height:56px;object-fit:contain;display:block;margin:0 auto 6px;border-radius:6px;background: rgba(0,0,0,0.25);">'
    else:
        icon_html = '<div style="width:56px;height:56px;margin:0 auto 6px;display:flex;align-items:center;justify-content:center;background: rgba(0,0,0,0.25);border-radius:6px;color:#e07a5f;font-size:22px;font-weight:700;">?</div>'

    return (
        '<div style="width:110px; border:var(--border-width, 2px) solid var(--border, rgba(255,255,255,0.12)); background:var(--slot, rgba(255,255,255,0.04)); border-radius:10px; padding:10px 8px; text-align:center; margin:8px;">'
        f'<div style="font-size:9px; color:#d9b994; margin-bottom:6px;">#{index + 1}</div>'
        f'{icon_html}'
        f'<div style="font-size:11px; font-weight:600; margin-top:6px;">{html.escape(spell_display_name(spell_id))}</div>'
        f'<div style="font-size:9px; color:#d9b994; margin-top:4px; word-break:break-word;">{html.escape(spell_id)}</div>'
        '</div>'
    )


def find_wand_sprite_path(wand):
    sprite_id = (wand.get("sprite_id") or "").strip()
    if sprite_id:
        sprite_path = WAND_SPRITE_DIR / f"{sprite_id}.png"
        if sprite_path.exists():
            return sprite_path

    sprite_file = (wand.get("sprite_file") or "").strip()
    if sprite_file:
        sprite_name = Path(sprite_file).stem
        sprite_path = WAND_SPRITE_DIR / f"{sprite_name}.png"
        if sprite_path.exists():
            return sprite_path

    return None


def render_wand_sprite(wand):
    sprite_path = find_wand_sprite_path(wand)
    if sprite_path:
        alt_text = wand.get("sprite_id") or wand.get("ui_name") or "wand sprite"
        return (
            '<div style="width:205px; min-width:205px; height:52px; display:flex; align-items:center; justify-content:center; background:transparent; border:none; padding:0; box-sizing:border-box; margin-right:18px; overflow:visible;">'
            f'<img src="{to_data_uri(sprite_path)}" alt="{html.escape(alt_text)}" style="max-width:100%; max-height:100%; width:auto; height:100%; object-fit:contain; display:block;">'
            '</div>'
        )

    return (
        '<div style="width:820px; min-width:820px; height:210px; display:flex; align-items:center; justify-content:center; background:rgba(255,255,255,0.02); border:1px dashed rgba(255,255,255,0.24); border-radius:12px; color:#d9b994; font-weight:bold; font-size:12px; margin-right:18px;">'
        'No wand sprite'
        '</div>'
    )


def render_wand_section(wand):
    reload_s = wand["reload_time_frames"] / 60.0
    delay_s = wand["spellcast_delay_frames"] / 60.0

    shuffle_value = wand.get("shuffle_deck_when_empty", 0)
    if isinstance(shuffle_value, str):
        shuffle_label = "Yes" if shuffle_value.strip().lower() in {"true", "yes", "1", "y"} else "No"
    else:
        shuffle_label = "Yes" if bool(shuffle_value) else "No"

    stat_values = [
        ("WAND", html.escape(wand.get("ui_name") or "Wand")),
        ("CAPACITY", wand["deck_capacity"]),
        ("SPELLS", len(wand["spells"])),
        ("RELOAD", f'{wand["reload_time_frames"]:.0f}f ({reload_s:.2f}s)'),
        ("CAST", f'{wand["spellcast_delay_frames"]:.0f}f ({delay_s:.2f}s)'),
        ("MANA", f'{wand["mana_max"]:.0f}'),
        ("SPREAD", f'{wand["spread_degrees"]:.0f}°'),
        ("SHUFFLE", shuffle_label),
    ]

    stats = "".join(
        f'<div style="display:flex; flex-direction:column; margin-right:18px; min-width:90px;">'
        f'<div style="font-size:11px; text-transform:uppercase; letter-spacing:1px; color:#d9b994; margin-bottom:4px;">{html.escape(str(label))}</div>'
        f'<div style="font-size:18px; font-weight:700; color:#f2efe9; font-family:Consolas, Monaco, monospace;">{html.escape(str(value))}</div>'
        '</div>'
        for label, value in stat_values
    )

    cards = []
    for index, spell_id in enumerate(wand["spells"]):
        cards.append(render_spell_card(index, spell_id))

    for _ in range(max(0, wand["deck_capacity"] - len(wand["spells"]))):
        cards.append('<div style="width:110px; border:var(--border-width, 2px) dashed var(--border, rgba(255,255,255,0.12)); background:var(--slot, rgba(255,255,255,0.04)); border-radius:10px; padding:10px 8px; text-align:center; margin:8px; opacity:0.7; min-height:110px; box-sizing:border-box;"></div>')

    return (
        '<section style="background:var(--wand-bg); border:var(--wand-border-width, 3px) solid var(--wand-border, rgba(255,255,255,0.08)); border-radius:0; overflow:hidden; margin-bottom:28px; padding:12px 0 0; box-shadow:0 0 0 1px rgba(0,0,0,0.4);">'
        '  <div style="display:flex; align-items:flex-start; gap:18px; padding:8px 18px 8px;">'
        f'    {render_wand_sprite(wand)}'
        '    <div style="flex:1; min-width:0; padding-top:8px;">'
        f'      <div style="font-size:22px; letter-spacing:2px; text-transform:uppercase; color:#f5f5f5; font-family:Consolas, Monaco, monospace; margin-bottom:12px;">{html.escape(wand.get("ui_name") or "WAND")}</div>'
        f'      <div style="display:flex; flex-wrap:wrap;">{stats}</div>'
        '    </div>'
        '  </div>'
        f'  <div style="display:flex; flex-wrap:wrap; padding:10px 18px 18px; gap:8px;">{"".join(cards)}</div>'
        '</section>'
    )


def render_results_page(file_names, wands):
    sections = "\n".join(render_wand_section(wand) for wand in wands)
    source_label = ", ".join(html.escape(name) for name in file_names[:5])
    if len(file_names) > 5:
        source_label += ", ..."
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Noita Wands</title>
  <style>
    :root {{
      --bg: #2e2522;
      --panel: #121212;
      --panel-alt: #171717;
      --text: #f3efe6;
      --muted: #d5cbb8;
      --accent: #b3d9ff;
      --slot: #2e2522;
      --border: #411b1a;
      --wand-border: #937e69;
      --wand-border-width: 3px;
      --wand-bg: #0e0c0b;
    }}
    body {{
      margin: 0;
      padding: 28px 20px 50px;
      background: var(--bg);
      color: var(--text);
      font-family: Consolas, Monaco, monospace;
    }}
    .page {{
      width: min(100%, 2000px);
      margin: 0 auto;
      padding-left: 12px;
      padding-right: 12px;
      box-sizing: border-box;
    }}
    h1 {{
      color: var(--text);
      margin-bottom: 8px;
      font-size: 32px;
      letter-spacing: 2px;
      text-transform: uppercase;
    }}
    .subtitle {{
      color: var(--muted);
      margin-bottom: 24px;
      font-size: 15px;
      letter-spacing: 0.5px;
    }}
    .wand-card {{
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 12px;
      margin-bottom: 24px;
      overflow: hidden;
    }}
    .wand-header {{
      padding: 16px 20px 8px;
    }}
    .wand-label {{
      font-size: 20px;
      letter-spacing: 2px;
      text-transform: uppercase;
      margin-bottom: 12px;
      color: var(--text);
    }}
    .wand-meta {{
      display: flex;
      flex-wrap: wrap;
      gap: 20px;
    }}
    .meta-block {{
      min-width: 110px;
      color: var(--muted);
      font-size: 12px;
      letter-spacing: 0.08em;
    }}
    .meta-value {{
      color: var(--text);
      font-weight: 700;
      font-size: 18px;
      margin-top: 4px;
    }}
    .wand-body {{
      display: flex;
      align-items: flex-start;
      gap: 18px;
      padding: 8px 20px 18px;
      flex-wrap: wrap;
    }}
    .wand-sprite {{
      width: 170px;
      height: 170px;
      display: flex;
      align-items: center;
      justify-content: center;
      background: transparent;
    }}
    .wand-sprite img {{
      max-width: 100%;
      max-height: 100%;
      object-fit: contain;
      filter: drop-shadow(0 0 8px rgba(105, 206, 255, 0.9));
    }}
    .spell-row {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      flex: 1;
      min-width: 0;
    }}
    .spell-card {{
      width: 110px;
      background: var(--slot);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 8px 6px;
      text-align: center;
    }}
    .spell-card img {{
      width: 56px;
      height: 56px;
      display: block;
      margin: 0 auto 6px;
      object-fit: contain;
      border-radius: 6px;
      background: rgba(0,0,0,0.2);
    }}
    .spell-card .missing-icon {{
      width: 56px;
      height: 56px;
      display: flex;
      align-items: center;
      justify-content: center;
      margin: 0 auto 6px;
      border-radius: 6px;
      background: rgba(255,255,255,0.06);
      color: #e07a5f;
      font-weight: 700;
      font-size: 22px;
    }}
    .spell-name {{
      font-size: 11px;
      font-weight: 600;
      line-height: 1.25;
      color: var(--text);
    }}
    .spell-id {{
      font-size: 9px;
      color: var(--muted);
      margin-top: 4px;
      word-break: break-word;
    }}
    .score-empty {{
      width: 110px;
      height: 110px;
      border: 1px dashed rgba(255,255,255,0.18);
      border-radius: 8px;
      background: rgba(255,255,255,0.02);
      opacity: 0.45;
    }}
    a {{
      color: var(--accent);
    }}
  </style>
</head>
<body>
  <div class="page">
    <h1>Wands found in uploaded files</h1>
    <div class="subtitle">{len(wands)} wand(s) detected across: {source_label}</div>
    {sections}
    <p><a href="/">Upload another file</a></p>
  </div>
</body>
</html>"""


class WandUploadHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(INDEX_HTML.encode("utf-8"))
            return

        self.send_response(404)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"Not found")

    def do_POST(self):
        if self.path != "/upload":
            self.send_response(404)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"Not found")
            return

        content_length = int(self.headers.get("Content-Length", "0"))
        raw_data = self.rfile.read(content_length)
        content_type = self.headers.get("Content-Type", "")

        try:
            form_data = parse_upload_data(raw_data, content_type)
            uploaded_files = form_data.get("bones_files", [])
            if not uploaded_files:
                raise ValueError("No files were uploaded.")

            xml_payloads = []
            file_names = []
            for uploaded in uploaded_files:
                file_name = uploaded["filename"] or "uploaded_file"
                if not file_name.lower().endswith((".xml", ".txt", ".bin")):
                    continue
                xml_text = uploaded["content"].decode("utf-8", errors="replace")
                xml_payloads.append((file_name, xml_text))
                file_names.append(file_name)

            if not xml_payloads:
                raise ValueError("No XML files were found in the uploaded selection.")

            wands = parse_wands_from_folder(xml_payloads)
            if not wands:
                raise ValueError("No wand entities were found in the uploaded files.")

            page = render_results_page(file_names, wands)
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(page.encode("utf-8"))
        except Exception as exc:
            error_page = f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><title>Upload error</title></head>
<body style="font-family:Arial,sans-serif;padding:32px;background:#1e120d;color:#f4e7d2;">
  <h1 style="color:#f0b35c;">Could not parse the uploaded file(s)</h1>
  <p>{html.escape(str(exc))}</p>
  <p><a href="/" style="color:#f0b35c;">Try another selection</a></p>
</body>
</html>"""
            self.send_response(400)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(error_page.encode("utf-8"))

    def log_message(self, format, *args):
        return


if __name__ == "__main__":
    server = ThreadingHTTPServer((HOST, PORT), WandUploadHandler)
    print(f"Serving Noita Wand Visualizer at http://localhost:{PORT}")
    server.serve_forever()
