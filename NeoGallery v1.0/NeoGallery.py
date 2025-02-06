import os
import json
import re
import neocities
import requests
import webbrowser
from pathlib import Path
from flask import Flask, request, jsonify, abort
from PIL import Image, ImageSequence
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
from waitress import serve
load_dotenv()

# ----------------------- CONFIGURATION -----------------------
class Config:
    def __init__(self):
        self.BASE_DIR = Path(__file__).parent
        
        self.STATIC_URL_PATH = os.environ.get("STATIC_URL_PATH", "/assets")
        self.STATIC_FOLDER = self.BASE_DIR / os.environ.get("STATIC_FOLDER", "static/assets")
        self.JSON_DIR = self.STATIC_FOLDER / os.environ.get("JSON_SUBDIR", "json")
        
        self.ALL_ART_JSON = self.JSON_DIR / os.environ.get("ALL_ART_JSON", "allArt.json")
        self.TAG_LIST_JSON = self.JSON_DIR / os.environ.get("TAG_LIST_JSON", "tag_list.json")

        self.TEMPLATE_DIR = self.BASE_DIR / os.environ.get("TEMPLATE_DIR", "templates")
        self.ART_HTML = self.TEMPLATE_DIR / os.environ.get("ART_HTML", "art.html")
        self.TAG_TEMPLATE = self.TEMPLATE_DIR / os.environ.get("TAG_TEMPLATE", "tagTemplate.html")
        self.INDEX_HTML = self.TEMPLATE_DIR / os.environ.get("INDEX_HTML", "index.html")

        # Asset directories (local)
        self.ART_DIR = self.STATIC_FOLDER / os.environ.get("ART_SUBDIR", "art")
        self.THUMB_DIR = self.STATIC_FOLDER / os.environ.get("THUMB_SUBDIR", "thumbnails")

        self.NEOCITIES_ART_DIR = os.environ.get("NEOCITIES_ART_DIR", "assets/media")
        self.NEOCITIES_THUMB_DIR = os.environ.get("NEOCITIES_THUMB_DIR", "assets/thumbnails")
        self.NEOCITIES_JSON_DIR = os.environ.get("NEOCITIES_JSON_DIR", "assets/json")

        # Neocities credentials
        self.API_KEY = os.environ.get('NEOCITIES_API_KEY')
        self.USER = os.environ.get('NEOCITIES_USER')
        self.PASS = os.environ.get('NEOCITIES_PASS')

        # Server configuration
        self.HOST = os.environ.get("FLASK_HOST", "127.0.0.1")
        self.PORT = int(os.environ.get("FLASK_PORT", "5000"))
        self.DEBUG = os.environ.get("FLASK_DEBUG", "True").lower() in ["true", "1", "yes"]
        
        # Pagination/Thumbnail settings
        self.DEFAULT_PER_PAGE = int(os.environ.get("DEFAULT_PER_PAGE", "10"))
        self.THUMBNAIL_WIDTH = int(os.environ.get("THUMBNAIL_WIDTH", "150"))

        # "random" tag name
        self.SHOW_IN_RANDOM = os.environ.get("SHOW_IN_RANDOM", "all")

        # Ensure directory structure
        self.TEMPLATE_DIR.mkdir(exist_ok=True)
        self.ART_DIR.mkdir(parents=True, exist_ok=True)
        self.THUMB_DIR.mkdir(parents=True, exist_ok=True)
        self.JSON_DIR.mkdir(parents=True, exist_ok=True)

        default_tag_snippet = """
<tr><td>
<a href="/__DATA_TAG__.html"><p class="headers">__LINK_TITLE__</p></a>
</td></tr>
"""  
        self.TAG_SECTION_TEMPLATE = os.environ.get("TAG_SECTION_TEMPLATE", default_tag_snippet)

# ----------------------- UTILITIES -----------------------
class FileUtils:
    @staticmethod
    def safe_json_load(path):
        try:
            if path.exists():
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return data if isinstance(data, list) else []
            return []
        except json.JSONDecodeError:
            abort(500, f"Corrupted JSON file: {path.name}")

    @staticmethod
    def safe_json_save(data, path):
        try:
            temp_path = path.with_suffix('.tmp')
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
            temp_path.replace(path)
        except IOError as e:
            abort(500, f"Failed to save {path.name}: {str(e)}")

class ImageProcessor:
    """Handles image processing with proper thumbnail generation."""

    THUMBNAIL_WIDTH = 150

    @classmethod
    def create_thumbnail(cls, src_path, dest_dir):
        dest_path = dest_dir / f"thumbnail_{src_path.name}"
        with Image.open(src_path) as img:
            if cls._is_animated_gif(img):
                cls._process_animated_gif(img, dest_path)
            else:
                cls._process_static_image(img, dest_path)
        return dest_path

    @staticmethod
    def _is_animated_gif(img):
        return img.format == 'GIF' and getattr(img, 'is_animated', False)

    @classmethod
    def _process_animated_gif(cls, img, dest_path):
        frames = []
        for frame in ImageSequence.Iterator(img):
            frames.append(cls._resize_frame(frame))
        frames[0].save(dest_path, save_all=True, append_images=frames[1:], loop=0)

    @classmethod
    def _process_static_image(cls, img, dest_path):
        resized = cls._resize_frame(img)
        resized.save(dest_path)

    @classmethod
    def _resize_frame(cls, frame):
        width_percent = cls.THUMBNAIL_WIDTH / float(frame.size[0])
        target_height = int(float(frame.size[1]) * width_percent)
        return frame.resize((cls.THUMBNAIL_WIDTH, target_height), Image.LANCZOS)

class NeocitiesUploader:
    def __init__(self, config):
        self.config = config

        # Check if credentials are provided
        if self.config.API_KEY:
            try:
                self.api = neocities.NeoCities(api_key=self.config.API_KEY)
            except Exception as e:
                print(f"[ERROR] Neocities API init failed: {str(e)}")
                self.api = None
        elif self.config.USER and self.config.PASS:
            try:
                self.api = neocities.NeoCities(self.config.USER, self.config.PASS)
            except Exception as e:
                print(f"[ERROR] Neocities API init failed: {str(e)}")
                self.api = None
        else:
            # Instead of crashing, log the missing key error and set api to None.
            print("Your neocities API key is missing")
            self.api = None

    def upload(self, local_path, remote_path):
        if self.api is None:
            print("Skipping upload: No Neocities API configured")
            return
        try:
            self.api.upload((str(local_path), remote_path))
        except requests.HTTPError as e:
            abort(500, f"Neocities upload failed: {str(e)}")

    def delete(self, remote_paths):
        if self.api is None:
            print("Skipping delete: No Neocities API configured")
            return
        try:
            if isinstance(remote_paths, list):
                self.api.delete(*remote_paths)
            else:
                self.api.delete(remote_paths)
        except requests.HTTPError as e:
            print(f"[ERROR] Delete failed: {e.response.text}")
            abort(500, f"Neocities delete failed: {str(e)}")


cfg = Config()
ImageProcessor.THUMBNAIL_WIDTH = cfg.THUMBNAIL_WIDTH

app = Flask(
    __name__,
    static_url_path=cfg.STATIC_URL_PATH,
    static_folder=str(cfg.STATIC_FOLDER)
)
uploader = NeocitiesUploader(cfg)

def _process_tags(tags_str):
    return [t.strip() for t in tags_str.split(",") if t.strip()]

@app.route("/")
def index():
    return cfg.INDEX_HTML.read_text(encoding='utf-8')

@app.route("/tags")
def get_tags():
    tags = FileUtils.safe_json_load(cfg.TAG_LIST_JSON)
    return jsonify({
        "tags": sorted(tags),
        "randomTag": cfg.SHOW_IN_RANDOM
    })

@app.route("/get_tag/<tag_name>")
def get_tag(tag_name):
    tags = FileUtils.safe_json_load(cfg.TAG_LIST_JSON)
    if tag_name not in tags:
        return jsonify({"error": f"Tag '{tag_name}' not found in registry"}), 404
    
    tag_html_path = cfg.TEMPLATE_DIR / f"{tag_name}.html"
    if not tag_html_path.exists():
        return jsonify({
            "error": f"Tag file {tag_name}.html not found",
            "tagName": tag_name,
            "metaDesc": "",
            "pageTitle": tag_name,
            "linkTitle": ""
        })

    content = tag_html_path.read_text(encoding='utf-8')
    meta_desc_match = re.search(r'<meta\s+name="description"\s+content="(.*?)"', content)
    page_title_match = re.search(r'<title>(.*?)</title>', content, re.DOTALL)

    art_html_content = cfg.ART_HTML.read_text(encoding='utf-8')
    section_match = re.search(
        rf'<!--{tag_name}-->(.*?)<!--END-->',
        art_html_content,
        re.DOTALL
    )
    link_title = ""
    if section_match:
        snippet = section_match.group(1)
        p_match = re.search(r'<p\s+class="tagText">(.*?)</p>', snippet, re.DOTALL)
        if p_match:
            link_title = p_match.group(1).strip()

    return jsonify({
        "tagName": tag_name,
        "metaDesc": meta_desc_match.group(1) if meta_desc_match else "",
        "pageTitle": page_title_match.group(1).strip() if page_title_match else tag_name,
        "linkTitle": link_title
    })

@app.route("/upload", methods=["POST"])
def upload_art():
    file = request.files.get("image")
    if not file or file.filename == '':
        abort(400, "Invalid image file")

    filename = secure_filename(file.filename)
    if not filename:
        abort(400, "Invalid filename")

    art_path = cfg.ART_DIR / filename
    file.save(art_path)

    thumb_path = ImageProcessor.create_thumbnail(art_path, cfg.THUMB_DIR)

    art_data = FileUtils.safe_json_load(cfg.ALL_ART_JSON)
    chosen_tags = request.form.get("chosen_tags", "")
    art_data.append({
        "thumbnailSrc": f"{cfg.NEOCITIES_THUMB_DIR}/{thumb_path.name}",
        "fullSrc": f"{cfg.NEOCITIES_ART_DIR}/{filename}",
        "title": request.form.get("title", ""),
        "description": request.form.get("description", ""),
        "tags": _process_tags(chosen_tags),
    })
    FileUtils.safe_json_save(art_data, cfg.ALL_ART_JSON)

    # Upload to Neocities
    uploader.upload(art_path, f"{cfg.NEOCITIES_ART_DIR}/{filename}")
    uploader.upload(thumb_path, f"{cfg.NEOCITIES_THUMB_DIR}/{thumb_path.name}")
    uploader.upload(cfg.ALL_ART_JSON, f"{cfg.NEOCITIES_JSON_DIR}/{cfg.ALL_ART_JSON.name}")

    return f"Successfully uploaded {filename}"

@app.route("/create_tag", methods=["POST"])
def create_tag():
    data = request.get_json()
    required_fields = ['tagName', 'metaDesc', 'pageTitle', 'linkTitle']
    if not all(data.get(field) for field in required_fields):
        abort(400, "Missing required tag fields")

    tag_page = cfg.TEMPLATE_DIR / f"{data['tagName']}.html"
    tag_page.write_text(
        cfg.TAG_TEMPLATE.read_text()
        .replace("__DATA_TAG__", data['tagName'])
        .replace("__META_DESC__", data['metaDesc'])
        .replace("__PAGE_TITLE__", data['pageTitle'])
    )

    _update_art_html(data['tagName'], data['linkTitle'])

    tags = FileUtils.safe_json_load(cfg.TAG_LIST_JSON)
    if data['tagName'] not in tags:
        tags.append(data['tagName'])
        FileUtils.safe_json_save(tags, cfg.TAG_LIST_JSON)

    uploader.upload(tag_page, tag_page.name)
    uploader.upload(cfg.ART_HTML, cfg.ART_HTML.name)
    
    uploader.upload(cfg.TAG_LIST_JSON, f"{cfg.NEOCITIES_JSON_DIR}/{cfg.TAG_LIST_JSON.name}")

    return f"Tag {data['tagName']} created successfully"

def _update_art_html(tag_name, link_title):
    content = cfg.ART_HTML.read_text(encoding='utf-8')
    last_end = content.rfind("<!--END-->")
    if last_end == -1:
        abort(400, "Missing <!--END--> marker in art.html")

    insertion_point = last_end + len("<!--END-->")
    
    snippet = cfg.TAG_SECTION_TEMPLATE
    snippet = snippet.replace("__DATA_TAG__", tag_name)
    snippet = snippet.replace("__LINK_TITLE__", link_title)

    new_section = f"\n<!--{tag_name}-->\n{snippet}\n<!--END-->\n"
    updated_content = content[:insertion_point] + new_section + content[insertion_point:]
    cfg.ART_HTML.write_text(updated_content, encoding='utf-8')

@app.route("/delete_tag", methods=["POST"])
def delete_tag():
    data = request.get_json()
    if not data or 'tagName' not in data:
        abort(400, "Missing tag name")

    tag_name = data['tagName']
    tags = FileUtils.safe_json_load(cfg.TAG_LIST_JSON)
    if tag_name not in tags:
        abort(404, f"Tag {tag_name} not found")

    tags.remove(tag_name)
    FileUtils.safe_json_save(tags, cfg.TAG_LIST_JSON)

    tag_page = cfg.TEMPLATE_DIR / f"{tag_name}.html"
    if tag_page.exists():
        tag_page.unlink()

    remove_tag_from_art_html(tag_name)
    purge_tag_from_art_entries(tag_name)

    uploader.upload(cfg.TAG_LIST_JSON, f"{cfg.NEOCITIES_JSON_DIR}/{cfg.TAG_LIST_JSON.name}")
    uploader.upload(cfg.ART_HTML, cfg.ART_HTML.name)
    uploader.upload(cfg.ALL_ART_JSON, f"{cfg.NEOCITIES_JSON_DIR}/{cfg.ALL_ART_JSON.name}")
    
    uploader.delete([f"{tag_name}.html"])
    return jsonify({"message": f"Tag {tag_name} deleted successfully"})

def remove_tag_from_art_html(tag_name):
    content = cfg.ART_HTML.read_text(encoding='utf-8')
    start_marker = f'<!--{tag_name}-->'
    start_idx = content.find(start_marker)
    if start_idx == -1:
        abort(404, f"Tag {tag_name} section not found in art.html")

    end_idx = content.find('<!--END-->', start_idx)
    if end_idx == -1:
        abort(400, f"No closing <!--END--> found for {tag_name}")
    end_idx += len('<!--END-->')

    updated_content = content[:start_idx] + content[end_idx:]
    cfg.ART_HTML.write_text(updated_content, encoding='utf-8')

def purge_tag_from_art_entries(tag_name):
    art_data = FileUtils.safe_json_load(cfg.ALL_ART_JSON)
    for entry in art_data:
        if tag_name in entry['tags']:
            entry['tags'].remove(tag_name)
    FileUtils.safe_json_save(art_data, cfg.ALL_ART_JSON)

@app.route("/edit_tag", methods=["POST"])
def edit_tag():
    data = request.get_json()
    required_fields = ['oldTagName', 'newTagName', 'metaDesc', 'pageTitle', 'linkTitle']
    if not all(field in data for field in required_fields):
        abort(400, "Missing required fields")

    old_tag = data['oldTagName']
    new_tag = data['newTagName']
    meta_desc = data['metaDesc']
    page_title = data['pageTitle']
    link_title = data['linkTitle']

    tags = FileUtils.safe_json_load(cfg.TAG_LIST_JSON)
    if old_tag not in tags:
        abort(404, f"Tag {old_tag} not found")
    if old_tag != new_tag and new_tag in tags:
        abort(400, f"Tag {new_tag} already exists")

    if old_tag != new_tag:
        tags.remove(old_tag)
        tags.append(new_tag)
        FileUtils.safe_json_save(tags, cfg.TAG_LIST_JSON)

    old_html = cfg.TEMPLATE_DIR / f"{old_tag}.html"
    new_html = cfg.TEMPLATE_DIR / f"{new_tag}.html"
    
    tag_content = cfg.TAG_TEMPLATE.read_text(encoding='utf-8')
    updated_content = (tag_content
        .replace("__DATA_TAG__", new_tag)
        .replace("__META_DESC__", meta_desc)
        .replace("__PAGE_TITLE__", page_title)
    )

    if old_tag != new_tag and old_html.exists():
        old_html.unlink()
    new_html.write_text(updated_content, encoding='utf-8')

    art_html_content = cfg.ART_HTML.read_text(encoding='utf-8')
    pattern = rf'(<!--{old_tag}-->)(.*?)(<!--END-->)'
    snippet = cfg.TAG_SECTION_TEMPLATE.strip()
    snippet = snippet.replace("__DATA_TAG__", new_tag)
    snippet = snippet.replace("__LINK_TITLE__", link_title)
    new_section = f'<!--{new_tag}-->\n{snippet}\n<!--END-->'

    updated_art_html = re.sub(pattern, new_section, art_html_content, flags=re.DOTALL)
    cfg.ART_HTML.write_text(updated_art_html, encoding='utf-8')

    if old_tag != new_tag:
        art_data = FileUtils.safe_json_load(cfg.ALL_ART_JSON)
        for entry in art_data:
            if old_tag in entry['tags']:
                entry['tags'].remove(old_tag)
                entry['tags'].append(new_tag)
        FileUtils.safe_json_save(art_data, cfg.ALL_ART_JSON)

    uploader.upload(cfg.TAG_LIST_JSON, f"{cfg.NEOCITIES_JSON_DIR}/{cfg.TAG_LIST_JSON.name}")
    uploader.upload(cfg.ART_HTML, cfg.ART_HTML.name)
    uploader.upload(cfg.ALL_ART_JSON, f"{cfg.NEOCITIES_JSON_DIR}/{cfg.ALL_ART_JSON.name}")
    uploader.upload(new_html, new_html.name)
    if old_tag != new_tag:
        uploader.delete([f"{old_tag}.html"])

    return jsonify({"message": f"Tag {old_tag} updated successfully"})

@app.route("/all_art")
def get_all_art():
    art_data = FileUtils.safe_json_load(cfg.ALL_ART_JSON)
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', cfg.DEFAULT_PER_PAGE, type=int)

    page = max(1, page)
    reversed_data = list(reversed(art_data))
    total_entries = len(reversed_data)
    total_pages = max(1, (total_entries + per_page - 1) // per_page)
    page = min(page, total_pages)

    start = (page - 1) * per_page
    end = start + per_page
    
    return jsonify({
        'artEntries': reversed_data[start:end],
        'totalPages': total_pages,
        'currentPage': page
    })

@app.route("/delete_art", methods=["POST"])
def delete_art():
    data = request.get_json()
    if not data or 'fullSrc' not in data:
        abort(400, "Missing art reference")

    art_data = FileUtils.safe_json_load(cfg.ALL_ART_JSON)
    entry = next((e for e in art_data if e['fullSrc'] == data['fullSrc']), None)
    if not entry:
        abort(404, "Art entry not found")

    art_data.remove(entry)
    FileUtils.safe_json_save(art_data, cfg.ALL_ART_JSON)

    art_file = cfg.ART_DIR / Path(entry['fullSrc']).name
    thumb_file = cfg.THUMB_DIR / Path(entry['thumbnailSrc']).name
    art_file.unlink(missing_ok=True)
    thumb_file.unlink(missing_ok=True)

    uploader.delete([
        f"{cfg.NEOCITIES_ART_DIR}/{art_file.name}",
        f"{cfg.NEOCITIES_THUMB_DIR}/{thumb_file.name}"
    ])
    uploader.upload(cfg.ALL_ART_JSON, f"{cfg.NEOCITIES_JSON_DIR}/{cfg.ALL_ART_JSON.name}")
    return jsonify({"message": f"Deleted {art_file.name}"})

@app.route("/edit_art", methods=["POST"])
def edit_art():
    data = request.get_json()
    if not data or 'originalSrc' not in data:
        abort(400, "Missing art reference")

    art_data = FileUtils.safe_json_load(cfg.ALL_ART_JSON)
    entry = next((e for e in art_data if e['fullSrc'] == data['originalSrc']), None)
    if not entry:
        abort(404, "Art entry not found")

    entry['title'] = data.get('title', entry['title'])
    entry['description'] = data.get('description', entry['description'])
    new_tags_str = ",".join(data.get('tags', entry['tags']))
    entry['tags'] = _process_tags(new_tags_str)

    FileUtils.safe_json_save(art_data, cfg.ALL_ART_JSON)
    uploader.upload(cfg.ALL_ART_JSON, f"{cfg.NEOCITIES_JSON_DIR}/{cfg.ALL_ART_JSON.name}")

    return jsonify({"message": "Art updated successfully"})

if __name__ == "__main__":
    if not cfg.API_KEY and not (cfg.USER and cfg.PASS):
        print("You will not be able to use this program! please add your API key to the .env under NEOCITIES_API_KEY, and relaunch.")
        input("Press any key to exit program...")
    else:
        print("""Welcome to...
  _   _             ____       _ _                                  _   ___  
 | \ | | ___  ___  / ___| __ _| | | ___ _ __ _   _  __   _____ _ __/ | / _ \ 
 |  \| |/ _ \/ _ \| |  _ / _` | | |/ _ \ '__| | | | \ \ / / _ \ '__| || | | |
 | |\  |  __/ (_) | |_| | (_| | | |  __/ |  | |_| |  \ V /  __/ |  | || |_| |
 |_| \_|\___|\___/ \____|\__,_|_|_|\___|_|   \__, |   \_/ \___|_|  |_(_)___/ 
                                             |___/         Author: KingPoss""")
        print(f"Hosted at: {cfg.HOST}:{cfg.PORT}")
        webbrowser.open(f"http://{cfg.HOST}:{cfg.PORT}", new = 1)
        serve(app, host=cfg.HOST, port=cfg.PORT, threads=100)
