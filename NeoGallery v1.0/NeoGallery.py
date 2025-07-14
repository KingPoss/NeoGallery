#!/usr/bin/env python
import os
import sys
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

# ------------------------------------------------------------------------------
# 1. SET THE BASE DIRECTORY ACCORDING TO THE RUNNING CONTEXT
#
# When running normally, use the directory of the source file.
# When frozen (with PyInstaller), use the current working directory.
# This way any files that you write (templates, JSON, etc.) are placed
# in a writable folder, not inside the read-only bundled folder.
# ------------------------------------------------------------------------------
if getattr(sys, 'frozen', False):
    BASE_DIR = Path(os.getcwd())
else:
    BASE_DIR = Path(__file__).parent

# Load environment variables from a .env file located in the working directory.
load_dotenv(dotenv_path=BASE_DIR / ".env")

# ----------------------- CONFIGURATION -----------------------
class Config:
    
    def __init__(self):
        # Use the appropriate base directory depending on frozen status.
        self.BASE_DIR = BASE_DIR

        # Folders and file paths – note that these paths are relative to BASE_DIR.
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
        self.TAG_COVERS_DIR = self.STATIC_FOLDER / "tag_covers"
        self.NEOCITIES_TAG_COVERS_DIR = os.environ.get("NEOCITIES_TAG_COVERS_DIR", "assets/tag_covers")
        # Remote directories for Neocities uploads
        self.NEOCITIES_ART_DIR = os.environ.get("NEOCITIES_ART_DIR", "assets/media")
        self.NEOCITIES_THUMB_DIR = os.environ.get("NEOCITIES_THUMB_DIR", "assets/thumbnails")
        self.NEOCITIES_JSON_DIR = os.environ.get("NEOCITIES_JSON_DIR", "assets/json")
        self.NEOCITIES_GALLERY_DIR = os.environ.get("NEOCITIES_GALLERY_DIR", "")
        self.NEOCITIES_TAG_DIR = os.environ.get("NEOCITIES_TAG_DIR", "")

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

        # Default tag snippet
        default_tag_snippet = """
<tr><td>
<a href="/__DATA_TAG__.html"><p class="headers">__LINK_TITLE__</p></a>
</td></tr>
"""  
        self.TAG_SECTION_TEMPLATE = os.environ.get("TAG_SECTION_TEMPLATE", default_tag_snippet)

        # ------------------ ENSURE DIRECTORY STRUCTURE ------------------
        # Make sure these directories exist. (They are assumed writable.)
        self.TEMPLATE_DIR.mkdir(exist_ok=True)
        self.ART_DIR.mkdir(parents=True, exist_ok=True)
        self.THUMB_DIR.mkdir(parents=True, exist_ok=True)
        self.JSON_DIR.mkdir(parents=True, exist_ok=True)
        self.TAG_COVERS_DIR.mkdir(parents=True, exist_ok=True)

    def get_gallery_path(self, filename):
        if self.NEOCITIES_GALLERY_DIR:
            return f"{self.NEOCITIES_GALLERY_DIR}/{filename}"
        return filename

    def get_tag_path(self, filename):
        if self.NEOCITIES_TAG_DIR:
            return f"{self.NEOCITIES_TAG_DIR}/{filename}"
        return filename

    def get_tag_dir(self):
        """
        Returns the remote tag directory.
        This is useful when you need to insert the tag directory into your templates.
        If NEOCITIES_TAG_DIR is empty, returns an empty string.
        """
        return self.NEOCITIES_TAG_DIR.strip() if self.NEOCITIES_TAG_DIR else ""

    def get_gallery_dir(self):
        """
        Returns the remote gallery directory.
        This is useful when you need to insert the gallery directory into your templates.
        If NEOCITIES_GALLERY_DIR is empty, returns an empty string.
        """
        return self.NEOCITIES_GALLERY_DIR.strip() if self.NEOCITIES_GALLERY_DIR else ""

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
            temp_path = path.with_suffix('.png')
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
            print("Your Neocities API key is missing")
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


# Initialize configuration and uploader
cfg = Config()
ImageProcessor.THUMBNAIL_WIDTH = cfg.THUMBNAIL_WIDTH
app = Flask(
    __name__,
    static_url_path=cfg.STATIC_URL_PATH,
    static_folder=str(cfg.STATIC_FOLDER)
)
uploader = NeocitiesUploader(cfg)

# ------------------------------------------------------------------------------
# HELPER FUNCTION TO WRAP ALL UPLOADER.UPLOAD CALLS
# ------------------------------------------------------------------------------
def perform_upload(upload_items):
    """
    Accepts a list of tuples (local_path, remote_path) and performs uploader.upload on each.
    """
    for local_path, remote_path in upload_items:
        # Only attempt upload if the file exists.
        if local_path.exists():
            uploader.upload(local_path, remote_path)
        else:
            print(f"Skipping upload for {local_path} as it does not exist.")

def _process_tags(tags_str):
    return [t.strip() for t in tags_str.split(",") if t.strip()]

# ----------------------- ROUTES -----------------------
@app.route("/")
def index():
    return cfg.INDEX_HTML.read_text(encoding='utf-8')

@app.route("/tags")
def get_tags():
    tags = FileUtils.safe_json_load(cfg.TAG_LIST_JSON)
    
    # Convert to simple list for backward compatibility
    tag_names = []
    for tag in tags:
        if isinstance(tag, str):
            tag_names.append(tag)
        elif isinstance(tag, dict):
            tag_names.append(tag.get('name'))
    
    return jsonify({
        "tags": sorted(tag_names),
        "randomTag": cfg.SHOW_IN_RANDOM
    })

@app.route("/get_tag/<tag_name>")
def get_tag(tag_name):
    tags = FileUtils.safe_json_load(cfg.TAG_LIST_JSON)
    
    # Find tag info (handle both string and dict formats)
    tag_info = None
    cover_photo = ""
    for tag in tags:
        if isinstance(tag, str) and tag == tag_name:
            tag_info = tag
            break
        elif isinstance(tag, dict) and tag.get('name') == tag_name:
            tag_info = tag.get('name')
            cover_photo = tag.get('coverPhoto', '')
            break
    
    if not tag_info:
        return jsonify({"error": f"Tag '{tag_name}' not found in registry"}), 404
    
    tag_html_path = cfg.TEMPLATE_DIR / f"{tag_name}.html"
    if not tag_html_path.exists():
        return jsonify({
            "error": f"Tag file {tag_name}.html not found",
            "tagName": tag_name,
            "metaDesc": "",
            "pageTitle": tag_name,
            "linkTitle": "",
            "coverPhoto": cover_photo
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
        "linkTitle": link_title,
        "coverPhoto": cover_photo
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

    # Upload to Neocities using perform_upload helper
    perform_upload([
        (art_path, f"{cfg.NEOCITIES_ART_DIR}/{filename}"),
        (thumb_path, f"{cfg.NEOCITIES_THUMB_DIR}/{thumb_path.name}"),
        (cfg.ALL_ART_JSON, f"{cfg.NEOCITIES_JSON_DIR}/{cfg.ALL_ART_JSON.name}")
    ])

    return f"Successfully uploaded {filename}"

@app.route("/create_tag", methods=["POST"])
def create_tag():
    # Handle both JSON and FormData
    if request.content_type and 'multipart/form-data' in request.content_type:
        # Handle form data with file upload
        data = {
            'tagName': request.form.get('tagName'),
            'metaDesc': request.form.get('metaDesc'),
            'pageTitle': request.form.get('pageTitle'),
            'linkTitle': request.form.get('linkTitle')
        }
        cover_file = request.files.get('coverPhoto')
    else:
        # Handle JSON data (backward compatibility)
        data = request.get_json()
        cover_file = None
    
    required_fields = ['tagName', 'metaDesc', 'pageTitle', 'linkTitle']
    if not all(data.get(field) for field in required_fields):
        abort(400, "Missing required tag fields")
    
    # Process cover photo if provided
    cover_photo_path = ""
    if cover_file and cover_file.filename:
        # Create thumbnail for cover photo
        cover_filename = f"cover_{data['tagName']}_{secure_filename(cover_file.filename)}"
        temp_path = cfg.TAG_COVERS_DIR / "temp_cover.png"
        cover_file.save(temp_path)
        
        # Create thumbnail (no full-size version needed)
        cover_thumb_path = ImageProcessor.create_thumbnail(temp_path, cfg.TAG_COVERS_DIR)
        final_cover_path = cfg.TAG_COVERS_DIR / cover_filename
        cover_thumb_path.rename(final_cover_path)
        temp_path.unlink()  # Remove temp file
        
        cover_photo_path = f"{cfg.NEOCITIES_TAG_COVERS_DIR}/{cover_filename}"
        
    # Create the tag page with cover photo
    tag_page = cfg.TEMPLATE_DIR / f"{data['tagName']}.html"
    tag_template = cfg.TAG_TEMPLATE.read_text(encoding='utf-8')
    tag_template = (
        tag_template
        .replace("__DATA_TAG__", data['tagName'])
        .replace("__META_DESC__", data['metaDesc'])
        .replace("__PAGE_TITLE__", data['pageTitle'])
        .replace("__COVER_PHOTO__", cover_photo_path)
        .replace("__NEOCITIES_GALLERY_DIR__", cfg.get_gallery_dir())
        .replace("__GALLERY_PAGE__", cfg.ART_HTML.name)
    )
    tag_page.write_text(tag_template, encoding='utf-8')
    
    _update_art_html(data['tagName'], data['linkTitle'], cover_photo_path)
    
    # Update tags list with cover photo info
    tags = FileUtils.safe_json_load(cfg.TAG_LIST_JSON)
    tag_info = {
        'name': data['tagName'],
        'coverPhoto': cover_photo_path
    }
    
    # Check if tag already exists
    existing_tag = next((t for t in tags if isinstance(t, dict) and t.get('name') == data['tagName']), None)
    if not existing_tag:
        # For backward compatibility, check if it's a string
        if data['tagName'] not in [t if isinstance(t, str) else t.get('name') for t in tags]:
            tags.append(tag_info)
    
    FileUtils.safe_json_save(tags, cfg.TAG_LIST_JSON)
    
    # Upload files
    upload_items = [
        (tag_page, cfg.get_tag_path(tag_page.name)),
        (cfg.ART_HTML, cfg.get_gallery_path(cfg.ART_HTML.name)),
        (cfg.TAG_LIST_JSON, f"{cfg.NEOCITIES_JSON_DIR}/{cfg.TAG_LIST_JSON.name}")
    ]
    
    if cover_photo_path and final_cover_path.exists():
        upload_items.append((final_cover_path, cover_photo_path))
    
    perform_upload(upload_items)
    
    return jsonify({"message": f"Tag {data['tagName']} created successfully"})


def _update_art_html(tag_name, link_title, cover_photo_path):
    content = cfg.ART_HTML.read_text(encoding='utf-8')
    last_end = content.rfind("<!--END-->")
    if last_end == -1:
        abort(400, "Missing <!--END--> marker in art.html")

    insertion_point = last_end + len("<!--END-->")
    
    # Get and format the tag directory.
    snippet = cfg.TAG_SECTION_TEMPLATE.strip()
    tag_dir = cfg.get_tag_dir()
    snippet = snippet.replace("__NEOCITIES_TAG_DIR__", tag_dir)
    
    snippet = snippet.replace("__DATA_TAG__", tag_name)
    snippet = snippet.replace("__LINK_TITLE__", link_title)
    snippet = snippet.replace("__COVER_PHOTO__", cover_photo_path)
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
    
    # Find and remove tag (handle both string and dict formats)
    tag_to_remove = None
    cover_photo_path = ""
    for i, tag in enumerate(tags):
        if isinstance(tag, str) and tag == tag_name:
            tag_to_remove = i
            break
        elif isinstance(tag, dict) and tag.get('name') == tag_name:
            tag_to_remove = i
            cover_photo_path = tag.get('coverPhoto', '')
            break
    
    if tag_to_remove is None:
        abort(404, f"Tag {tag_name} not found")
    
    tags.pop(tag_to_remove)
    FileUtils.safe_json_save(tags, cfg.TAG_LIST_JSON)
    
    tag_page = cfg.TEMPLATE_DIR / f"{tag_name}.html"
    if tag_page.exists():
        tag_page.unlink()
    
    # Delete local cover photo if exists
    if cover_photo_path:
        local_cover = cfg.TAG_COVERS_DIR / Path(cover_photo_path).name
        if local_cover.exists():
            local_cover.unlink()
    
    remove_tag_from_art_html(tag_name)
    purge_tag_from_art_entries(tag_name)
    
    perform_upload([
        (cfg.ART_HTML, cfg.get_gallery_path(cfg.ART_HTML.name)),
        (cfg.ALL_ART_JSON, f"{cfg.NEOCITIES_JSON_DIR}/{cfg.ALL_ART_JSON.name}")
    ])
    
    # Delete remote files
    files_to_delete = [cfg.get_tag_path(f"{tag_name}.html")]
    if cover_photo_path:
        files_to_delete.append(cover_photo_path)
    
    uploader.delete(files_to_delete)
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
    # Handle both JSON and FormData
    if request.content_type and 'multipart/form-data' in request.content_type:
        data = {
            'oldTagName': request.form.get('oldTagName'),
            'newTagName': request.form.get('newTagName'),
            'metaDesc': request.form.get('metaDesc'),
            'pageTitle': request.form.get('pageTitle'),
            'linkTitle': request.form.get('linkTitle')
        }
        cover_file = request.files.get('coverPhoto')
    else:
        data = request.get_json()
        cover_file = None
    
    required_fields = ['oldTagName', 'newTagName', 'metaDesc', 'pageTitle', 'linkTitle']
    if not all(field in data for field in required_fields):
        abort(400, "Missing required fields")
    
    old_tag = data['oldTagName']
    new_tag = data['newTagName']
    meta_desc = data['metaDesc']
    page_title = data['pageTitle']
    link_title = data['linkTitle']
    
    tags = FileUtils.safe_json_load(cfg.TAG_LIST_JSON)
    
    # Find existing tag
    tag_index = None
    existing_cover = ""
    for i, tag in enumerate(tags):
        if isinstance(tag, str) and tag == old_tag:
            tag_index = i
            break
        elif isinstance(tag, dict) and tag.get('name') == old_tag:
            tag_index = i
            existing_cover = tag.get('coverPhoto', '')
            break
    
    if tag_index is None:
        abort(404, f"Tag {old_tag} not found")
    
    # Check if new tag name already exists (if renaming)
    if old_tag != new_tag:
        for tag in tags:
            tag_name = tag if isinstance(tag, str) else tag.get('name')
            if tag_name == new_tag:
                abort(400, f"Tag {new_tag} already exists")
    
    # Process new cover photo if provided
    new_cover_path = existing_cover
    if cover_file and cover_file.filename:
        # Delete old cover if exists
        if existing_cover:
            old_cover_local = cfg.TAG_COVERS_DIR / Path(existing_cover).name
            if old_cover_local.exists():
                old_cover_local.unlink()
        
        # Create new cover
        cover_filename = f"cover_{new_tag}_{secure_filename(cover_file.filename)}"
        temp_path = cfg.TAG_COVERS_DIR / "temp_cover.png"
        cover_file.save(temp_path)
        
        cover_thumb_path = ImageProcessor.create_thumbnail(temp_path, cfg.TAG_COVERS_DIR)
        final_cover_path = cfg.TAG_COVERS_DIR / cover_filename
        cover_thumb_path.rename(final_cover_path)
        temp_path.unlink()
        
        new_cover_path = f"{cfg.NEOCITIES_TAG_COVERS_DIR}/{cover_filename}"
    
    # Update tag in list
    tags[tag_index] = {
        'name': new_tag,
        'coverPhoto': new_cover_path
    }
    FileUtils.safe_json_save(tags, cfg.TAG_LIST_JSON)
    
    # Update HTML files
    old_html = cfg.TEMPLATE_DIR / f"{old_tag}.html"
    new_html = cfg.TEMPLATE_DIR / f"{new_tag}.html"
    
    tag_content = cfg.TAG_TEMPLATE.read_text(encoding='utf-8')
    updated_content = (
        tag_content
        .replace("__DATA_TAG__", new_tag)
        .replace("__META_DESC__", meta_desc)
        .replace("__PAGE_TITLE__", page_title)
        .replace("__COVER_PHOTO__", new_cover_path)
        .replace("__NEOCITIES_GALLERY_DIR__", cfg.get_gallery_dir())
        .replace("__GALLERY_PAGE__", cfg.ART_HTML.name)
    )
    
    if old_tag != new_tag and old_html.exists():
        old_html.unlink()
    new_html.write_text(updated_content, encoding='utf-8')
    
    # Update art.html
    art_html_content = cfg.ART_HTML.read_text(encoding='utf-8')
    pattern = rf'(<!--{old_tag}-->)(.*?)(<!--END-->)'
    
    snippet = cfg.TAG_SECTION_TEMPLATE.strip()
    snippet = snippet.replace("__DATA_TAG__", new_tag)
    snippet = snippet.replace("__LINK_TITLE__", link_title)
    
    tag_dir = cfg.get_tag_dir()
    snippet = snippet.replace("__NEOCITIES_TAG_DIR__", tag_dir)
    
    new_section = f'<!--{new_tag}-->\n{snippet}\n<!--END-->'
    
    updated_art_html = re.sub(pattern, new_section, art_html_content, flags=re.DOTALL)
    cfg.ART_HTML.write_text(updated_art_html, encoding='utf-8')
    
    # Update art entries if tag name changed
    if old_tag != new_tag:
        art_data = FileUtils.safe_json_load(cfg.ALL_ART_JSON)
        for entry in art_data:
            if old_tag in entry['tags']:
                entry['tags'].remove(old_tag)
                entry['tags'].append(new_tag)
        FileUtils.safe_json_save(art_data, cfg.ALL_ART_JSON)
    
    # Prepare uploads
    upload_items = [
        (cfg.TAG_LIST_JSON, f"{cfg.NEOCITIES_JSON_DIR}/{cfg.TAG_LIST_JSON.name}"),
        (cfg.ART_HTML, cfg.get_gallery_path(cfg.ART_HTML.name)),
        (cfg.ALL_ART_JSON, f"{cfg.NEOCITIES_JSON_DIR}/{cfg.ALL_ART_JSON.name}"),
        (new_html, cfg.get_tag_path(new_html.name))
    ]
    
    if new_cover_path and (cfg.TAG_COVERS_DIR / Path(new_cover_path).name).exists():
        upload_items.append((cfg.TAG_COVERS_DIR / Path(new_cover_path).name, new_cover_path))
    
    perform_upload(upload_items)
    
    # Clean up old files on remote
    files_to_delete = []
    if old_tag != new_tag:
        files_to_delete.append(cfg.get_tag_path(f"{old_tag}.html"))
    if existing_cover and existing_cover != new_cover_path:
        files_to_delete.append(existing_cover)
    
    if files_to_delete:
        uploader.delete(files_to_delete)
    
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
    perform_upload([
        (cfg.ALL_ART_JSON, f"{cfg.NEOCITIES_JSON_DIR}/{cfg.ALL_ART_JSON.name}")
    ])
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
    perform_upload([
        (cfg.ALL_ART_JSON, f"{cfg.NEOCITIES_JSON_DIR}/{cfg.ALL_ART_JSON.name}")
    ])

    return jsonify({"message": "Art updated successfully"})

# ----------------------- ENTRY POINT -----------------------
if __name__ == "__main__":
    if not cfg.API_KEY and not (cfg.USER and cfg.PASS):
        print("You will not be able to use this program! Please add your API key to the .env under NEOCITIES_API_KEY, and relaunch.")
        input("Press any key to exit program...")
    else:
        if cfg.DEBUG:
            print(f"Hosted at: {cfg.HOST}:{cfg.PORT}")
            app.run(host=cfg.HOST, port=cfg.PORT, debug=True)
        else:
            print("""Welcome to...
 ______              ______       _ _                            __  __ 
|  ___ \            / _____)     | | |                          /  |/  |
| |   | | ____ ___ | /  ___  ____| | | ____  ____ _   _    _   /_/ /_/ |
| |   | |/ _  ) _ \| | (___)/ _  | | |/ _  )/ ___) | | |  | | | || | | |
| |   | ( (/ / |_| | \____/( ( | | | ( (/ /| |   | |_| |   \ V / | |_| |
|_|   |_|\____)___/ \_____/ \_||_|_|_|\____)_|    \__  |    \_/  |_(_)_|
                                                 (____/Author: KingPoss""")
            print(f"Hosted at: {cfg.HOST}:{cfg.PORT}")
            webbrowser.open(f"http://{cfg.HOST}:{cfg.PORT}", new=1)
            serve(app, host=cfg.HOST, port=cfg.PORT, threads=100)
